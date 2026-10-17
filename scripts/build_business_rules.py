#!/usr/bin/env python3
"""Build business-named drafts; keep exit preferences separate from identity."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import shutil
import tempfile
from audit_acl4ssr import build, parse_rule


def rule_host(rule):
    """Return the value part of a rule: 'DOMAIN-SUFFIX,auth0.com,g' -> 'auth0.com'."""
    parts = rule.split(',')
    return parts[1].strip() if len(parts) > 1 else ''


def host_matches(pattern, host):
    """Match a host against an ownership pattern using Clash semantics."""
    kind, _, value = pattern.partition(',')
    kind = kind.strip().upper()
    value = value.strip()
    if not value:
        return False
    if kind == 'DOMAIN':
        return host == value
    if kind == 'DOMAIN-SUFFIX':
        return host == value or host.endswith('.' + value)
    return False


def resolve_business(rule, source, sources, forced, layout):
    """Source-agnostic business ownership for one parsed rule.

    Precedence:
      1. exact rule override (layout['rule_overrides'])
      2. explicit host ownership (layout['ownership_overrides']) - wins over source mapping
      3. shared login/payment/telemetry hosts (layout['shared_hosts']) - applied to EVERY source,
         not only custom/AI_other.list
      4. region endpoints verified from real traffic/config (layout['observed_region_hosts'])
      5. the source's category mapping

    Source records are preserved by the caller (row['source'], provenance entries).
    Note: 'auth0.openai.com' is not covered by 'auth0.com' (different parent), so it keeps
    the ownership of its own source list.
    """
    if rule in forced:
        return forced[rule]
    host = rule_host(rule)
    if host:
        for pattern, business in layout.get('ownership_overrides', {}).items():
            if host_matches(pattern, host):
                return business
        if host in layout['shared_hosts']:
            return 'shared_services'
        for business, hosts in layout.get('observed_region_hosts', {}).items():
            if host in hosts:
                return business
    return sources.get(source, '')


def generate(root, seed_path, layout_path, output):
    seed = json.loads(seed_path.read_text(encoding='utf-8'))
    layout = json.loads(layout_path.read_text(encoding='utf-8'))
    businesses, roles = layout['businesses'], layout['roles']
    sources = {}
    for source, category in seed['sources'].items():
        target = layout['source_overrides'].get(source, layout['category_defaults'].get(category))
        if target:
            sources[source] = target
    sources.update(layout['extra_sources'])
    compiled = {'sources': sources, 'categories': {name: {'priority': item['priority'], 'node': roles[item['role']]['node']} for name, item in businesses.items()}}
    for name, item in businesses.items():
        constraint = layout['constraints'].get(name, {})
        region = roles[item['role']].get('region')
        if region in constraint.get('avoid_regions', []):
            raise RuntimeError('Default exit violates avoid-region policy: ' + name)
        if constraint.get('required_region') and region != constraint['required_region']:
            raise RuntimeError('Default exit violates required-region policy: ' + name)
    with tempfile.TemporaryDirectory(prefix='business-build-') as tmp:
        temp = Path(tmp)
        compiled_path = temp / 'policy.json'
        compiled_path.write_text(json.dumps(compiled), encoding='utf-8')
        staged = temp / 'output'
        build(root, compiled_path, staged)
        with (staged / 'rules.csv').open(encoding='utf-8-sig', newline='') as handle:
            records = list(csv.DictReader(handle))
        forced = {parse_rule(rule)[0]: business for rule, business in layout['rule_overrides'].items()}
        owners = defaultdict(list)
        held = defaultdict(list)
        for row in records:
            rule = row['rule']
            business = resolve_business(rule, row['source'], sources, forced, layout)
            row['category'] = business
            safe = row['safe_syntax'] == 'True'
            if safe and row['source'] in layout['review_sources']:
                held[rule].append(row['source'])
            if safe and business and row['source'].endswith('.list'):
                owners[rule].append({'source': row['source'], 'position': row['position'], 'business': business})
        injected = layout.get('injected_rules', {})
        for rule, business in sorted(injected.items()):
            if rule in forced:
                continue
            owners.setdefault(rule, []).append({'source': 'layout:injected', 'position': '0', 'business': business})
        chosen = {name: [] for name in businesses}
        conflicts, pending, provenance = [], [], {}
        for rule, candidates in sorted(owners.items()):
            assignments = sorted({item['business'] for item in candidates}, key=lambda name: (businesses[name]['priority'], name))
            if rule in held and set(assignments) <= {'general_overseas'} and rule not in forced:
                pending.append({'rule': rule, 'sources': held[rule], 'reason': 'legacy-mixed-source-needs-business-review'})
                continue
            winner = assignments[0]
            chosen[winner].append(rule)
            provenance[rule] = {'winner': winner, 'sources': candidates}
            if len(assignments) > 1:
                conflicts.append({'rule': rule, 'candidate_winner': winner, 'businesses': assignments, 'sources': candidates})
        for rule, held_sources in sorted(held.items()):
            if rule not in owners:
                pending.append({'rule': rule, 'sources': held_sources, 'reason': 'unclassified-legacy-rule'})
        for row in records:
            if row['safe_syntax'] == 'True' and row['rule'] in provenance:
                row['reason'] = 'candidate-business:' + provenance[row['rule']]['winner']
            elif row['safe_syntax'] == 'True' and row['rule'] in held:
                row['reason'] = 'pending-business-review'
        with (staged / 'rules.csv').open('w', encoding='utf-8-sig', newline='') as handle:
            fields = ['source','position','position_kind','rule','type','safe_syntax','category','reason']
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
        shutil.rmtree(staged / 'rules')
        (staged / 'rules').mkdir()
        plan = {'ready_for_production': False, 'roles': roles, 'standby_only': layout['standby_only'], 'businesses': {}}
        report = ['# 业务规则候选 v2', '', '按业务命名；出口映射与地区约束独立。不可直接部署。', '', '| 业务规则文件 | 候选条数 | 默认角色 |', '|---|---:|---|']
        for name, item in sorted(businesses.items(), key=lambda pair: pair[1]['priority']):
            (staged / 'rules' / (name + '.list')).write_text('# REVIEW ONLY; business=' + name + '\n' + '\n'.join(chosen[name]) + '\n', encoding='utf-8')
            plan['businesses'][name] = {'file': 'rules/' + name + '.list', 'default_role': item['role'], 'proposed_constraints': layout['constraints'].get(name, {}), 'candidate_count': len(chosen[name])}
            report.append('| ' + name + '.list | ' + str(len(chosen[name])) + ' | ' + item['role'] + ' |')
        summary = json.loads((staged / 'summary.json').read_text())
        summary.update({'business_layout_version': 2, 'category_counts': {name: len(values) for name, values in chosen.items()}, 'candidate_rules': sum(map(len, chosen.values())), 'cross_category_conflicts': len(conflicts), 'pending_legacy_rules': len(pending), 'ready_for_production': False})
        for filename, value in [('summary.json', summary), ('conflicts.json', conflicts), ('provenance.json', provenance), ('pending-business-review.json', pending), ('business-plan.json', plan), ('layout-used.json', layout)]:
            (staged / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report += ['', '- 上游提交：`' + summary['upstream_commit'] + '`', '- 候选规则：' + str(summary['candidate_rules']), '- 跨业务精确冲突：' + str(len(conflicts)), '- 旧混合列表待分类：' + str(len(pending)), '', '## 边界', '', '- 地区约束为拟定策略，不是逐域名地区验证结果。业务文件不绑定节点名。', '- 原分类 core/ai_kr/hk_required/jp_required/bulk/video/general 不作为新规则文件名。', '- adult_content 仅按策略避开韩国，不等于日本限定。DMM/AbemaTV/HuluJapan 独立保留业务身份。', '- 不设置额外核心交互列表：GitHub 网页/API 归 github_web_api，Copilot 与 Perplexity 归 ai_other；两类业务共同选择大阪 core_exit，GitHub 下载独立选择东京 capacity_exit。', '- Copilot 精确端点和下载精确端点的跨文件匹配顺序仍需验收；候选归属不等于已部署的实际路由。', '- 共享登录/支付/遥测主机从 AI_other 来源拆入 shared_services；其他来源冲突仍需审核。', '- 旧地区混合列表中的精确同名通用候选暂缓；未完成父域覆盖、IP 重叠及最终顺序分析，不能认为间接覆盖也已解除。', '- cloud_sync/游戏等是待审分类，直连与代理需求尚须验证。', '- 所有原解析记录保留；关键词等仍不进入候选，MRS 不解码。', '- inventory.csv 的 selected_category 代表来源初始分类；rules.csv/provenance.json 反映本轮覆盖后的业务归属。', '- 不生成生产 INI，不修改现有根目录规则，不自动提交候选。']
        (staged / 'REPORT.md').write_text('\n'.join(report) + '\n', encoding='utf-8')
        if output.exists():
            raise RuntimeError('Output must not already exist; choose a fresh directory')
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staged, output)
        print(json.dumps(summary, ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--layout', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    generate(args.root.resolve(), args.seed.resolve(), args.layout.resolve(), args.output.resolve())
