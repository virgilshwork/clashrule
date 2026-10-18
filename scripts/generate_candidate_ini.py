#!/usr/bin/env python3
"""Emit a self-contained SubConverter candidate INI from business artifacts."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
from audit_acl4ssr import parse_rule

LEAVES = {
    'OSAKA_Premium': ('🗾 大阪Premium', 'JP'),
    'KR_Evoxt': ('🇰🇷 Evoxt韩国', 'KR'),
    'HK_Evoxt': ('🇭🇰 Evoxt香港', 'HK'),
    'TOKYO_Standby': ('🛟 东京容量', 'JP'),
    'GGC_HK_B': ('🟧 GGC香港B', 'HK'),
    'GGC_HK_A': ('🟨 GGC香港A', 'HK'),
}
ROLE_NAMES = {'direct': 'DIRECT', 'reject': 'REJECT', 'core_exit': '🟢 核心出口', 'general_exit': '🟡 普通海外', 'hk_exit': '🌍 香港出口', 'capacity_exit': '📦 容量出口', 'jp_exit': '🌍 日本出口'}
BUSINESS_NAMES = {
    'direct': 'Ⓜ️ Direct', 'block': '🛑 广告拦截', 'openai_anthropic': '🤖 OpenAI-Anthropic',
    'ai_other': '🧠 其他AI', 'github_web_api': '🐙 GitHub交互', 'github_bulk': '📦 GitHub下载',
    'overseas_download': '📦 海外下载', 'youtube': '📹 油管视频', 'streaming_other': '🎬 其他视频',
    'netflix': '🎥 奈飞视频', 'spotify': '🎵 Spotify', 'cloud_sync': '☁️ 云同步',
    'microsoft_services': 'Ⓜ️ 微软服务', 'telegram': '📲 电报消息', 'crypto': 'Ⓜ️ 加密货币',
    'mining': '⛏️ 挖矿业务', 'apple_store': '🍎 苹果商店', 'gaming_services': '🎮 游戏服务',
    'gaming_download': '🎮 游戏下载', 'shared_services': '🔗 共享依赖', 'general_overseas': '🌐 普通海外业务',
    'adult_content': '🔞 成人内容', 'google_play': '🌍 Google Play', 'mytvsuper': '📺 MyTVSuper',
    'viutv': '📺 ViuTV', 'hbo_go_hk': '📺 HBO香港', 'dmm': '📺 DMM', 'abematv': '📺 AbemaTV',
    'hulu_japan': '📺 Hulu Japan', 'niconico': '📺 Niconico', 'pixiv': '🎨 Pixiv',
    'japan_download': '📥 日本下载',
}

def sort_key(item, priorities):
    rule, business = item
    parts = rule.split(',')
    if parts[0] in ('DOMAIN', 'DOMAIN-SUFFIX'):
        host = parts[1]
        return (0, -len(host.split('.')), 0 if parts[0] == 'DOMAIN' else 1, priorities[business], host, business)
    net = ipaddress.ip_network(parts[1])
    return (1, -net.prefixlen, net.version, priorities[business], str(net), business)

def match_host(host, ordered):
    for rule, business in ordered:
        parts = rule.split(',')
        if parts[0] == 'DOMAIN' and host == parts[1]:
            return business
        if parts[0] == 'DOMAIN-SUFFIX' and (host == parts[1] or host.endswith('.' + parts[1])):
            return business
    return None

def emit(folder):
    plan = json.loads((folder / 'business-plan.json').read_text(encoding='utf-8'))
    layout = json.loads((folder / 'layout-used.json').read_text(encoding='utf-8'))
    summary = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
    businesses, roles = plan['businesses'], plan['roles']
    if 'core_interactive' in businesses:
        raise RuntimeError('Obsolete business layout; regenerate candidates first')
    if set(businesses) - set(BUSINESS_NAMES) or set(roles) - set(ROLE_NAMES):
        raise RuntimeError('Unknown business or role; review INI labels')
    priorities = {name: definition['priority'] for name, definition in layout['businesses'].items()}
    rules = []
    for business, definition in businesses.items():
        relative = Path(definition['file'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] != 'rules':
            raise RuntimeError('Unsafe rules path')
        values = []
        for line in (folder / relative).read_text(encoding='utf-8-sig').splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            normalized, _, safe, reason = parse_rule(line)
            if not safe:
                raise RuntimeError('Unsupported candidate: ' + line + ' / ' + reason)
            values.append(normalized)
        if len(values) != definition['candidate_count']:
            raise RuntimeError('Candidate count mismatch: ' + business)
        rules.extend((rule, business) for rule in values)
    if len({rule for rule, _ in rules}) != len(rules):
        raise RuntimeError('Duplicate candidate rules across businesses')
    ordered = sorted(rules, key=lambda item: sort_key(item, priorities))
    expected = {
        'github.com': 'github_web_api', 'api.github.com': 'github_web_api',
        'api.githubcopilot.com': 'ai_other', 'copilot-proxy.githubusercontent.com': 'ai_other',
        'perplexity.ai': 'ai_other', 'codeload.github.com': 'github_bulk',
        'release-assets.githubusercontent.com': 'github_bulk',
    }
    cases = [{'host': host, 'expected': business, 'actual': match_host(host, ordered)} for host, business in expected.items()]
    if any(case['actual'] != case['expected'] for case in cases):
        raise RuntimeError('Domain-order checks failed: ' + json.dumps(cases))
    if roles[businesses['github_web_api']['default_role']]['node'] != roles[businesses['ai_other']['default_role']]['node']:
        raise RuntimeError('GitHub/Copilot interactive default exits differ')
    groups = []
    for node, (label, _) in LEAVES.items():
        groups.append('custom_proxy_group=' + label + '`select`(^' + node + '$)`[]REJECT')
    for role, definition in roles.items():
        if role in ('direct', 'reject'):
            if definition['node'] != ROLE_NAMES[role]:
                raise RuntimeError('Unexpected built-in action')
            continue
        node = definition['node']
        if node not in LEAVES:
            raise RuntimeError('Unknown physical node: ' + node)
        groups.append('custom_proxy_group=' + ROLE_NAMES[role] + '`select`[]' + LEAVES[node][0] + '`[]REJECT')
    for business, definition in businesses.items():
        role = definition['default_role']
        constraint = definition.get('proposed_constraints', {})
        node = roles[role]['node']
        region = LEAVES[node][1] if node in LEAVES else None
        if constraint.get('required_region') and region != constraint['required_region']:
            raise RuntimeError('Required-region mismatch: ' + business)
        if region in constraint.get('avoid_regions', []):
            raise RuntimeError('Avoid-region mismatch: ' + business)
        options = [ROLE_NAMES[role]]
        if role not in ('direct', 'reject'):
            for standby in plan['standby_only']:
                label, standby_region = LEAVES[standby]
                if constraint.get('required_region') and standby_region != constraint['required_region']:
                    continue
                if standby_region in constraint.get('avoid_regions', []):
                    continue
                options.append(label)
        options.append('DIRECT' if role == 'reject' else 'REJECT')
        options = list(dict.fromkeys(options))
        groups.append('custom_proxy_group=' + BUSINESS_NAMES[business] + '`select`' + '`'.join('[]' + option for option in options))
    lines = ['[custom]', '; Generated candidate; NOT production-approved.', '; Based on virgil-v2.ini syntax, with business rules embedded inline.', '; Upstream snapshot: ' + summary['upstream_commit'], '; No remote ruleset URLs; no candidate-list publication is required.', '; All selectors are manual; GGC nodes are standby choices only.', '; Missing physical nodes retain REJECT rather than an empty role group.', '; Existing cached selector choices can override the intended first choice.', '; Domain rules precede IP rules; deeper hosts precede parents; exact precedes suffix at equal depth.', '; IP prefixes are ordered longest first. Business priorities only break specificity ties.', '; This is a proposed ordering, not proof that every overlap or business requirement is resolved.', '']
    for rule, business in ordered:
        lines.append('ruleset=' + BUSINESS_NAMES[business] + ',[]' + rule)
    lines += ['ruleset=Ⓜ️ Direct,[]GEOIP,CN', 'ruleset=🌐 普通海外业务,[]FINAL', '', '; Physical node groups, logical roles, then business selectors.']
    lines += groups
    lines += ['', 'enable_rule_generator=true', 'overwrite_original_rules=true', '']
    names = [line.split('=', 1)[1].split('`', 1)[0] for line in groups]
    if len(names) != len(set(names)):
        raise RuntimeError('Duplicate strategy group names')
    known = set(names) | {'DIRECT', 'REJECT'}
    for line in groups:
        for option in line.split('`')[2:]:
            if option.startswith('[]') and option[2:] not in known:
                raise RuntimeError('Unknown group reference: ' + option)
    for line in lines:
        if line.startswith('ruleset=') and line.split('=', 1)[1].split(',', 1)[0] not in known:
            raise RuntimeError('Unknown ruleset target: ' + line)
    content = '\n'.join(lines)
    (folder / 'virgil-candidate.ini').write_text(content, encoding='utf-8')
    check = {'ready_for_production': False, 'inline_rule_count': len(ordered) + 2, 'strategy_groups': len(groups), 'ini_sha256': hashlib.sha256(content.encode()).hexdigest(), 'domain_order_cases': cases, 'validation': 'Offline syntax/reference/domain-order checks only; no SubConverter or mihomo execution', 'review_required': ['pending-business-review.json', 'conflicts.json', 'parse-issues.json', 'domain versus IP ordering', 'selector cache and actual node availability', 'SubConverter inline-rule limits and generated YAML validation', 'business and authentication tests']}
    (folder / 'ini-validation.json').write_text(json.dumps(check, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with (folder / 'REPORT.md').open('a', encoding='utf-8') as handle:
        handle.write('\n## 候选 INI\n\n已生成 virgil-candidate.ini（自包含内嵌规则），角色/业务组 ' + str(len(groups)) + ' 个，规则 ' + str(len(ordered) + 2) + ' 条。七项域名首匹配检查通过；未执行实际订阅转换或 mihomo 验收，仍不可直接部署。详见 ini-validation.json。\n')
    print(json.dumps(check, ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    emit(args.input.resolve())
