#!/usr/bin/env python3
"""Audit every snapshot file and generate review-only business rule candidates."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import yaml

DOMAIN_TYPES = {'DOMAIN', 'DOMAIN-SUFFIX'}
IP_TYPES = {'IP-CIDR', 'IP-CIDR6'}

def parse_rule(text):
    text = text.strip()
    parts = [p.strip() for p in text.split(',')]
    kind = parts[0].upper()
    if kind in DOMAIN_TYPES:
        if len(parts) != 2:
            return text, kind, False, 'invalid-domain-arity'
        domain = parts[1].lower().rstrip('.')
        try:
            domain = domain.encode('idna').decode('ascii')
        except UnicodeError:
            return text, kind, False, 'invalid-idna'
        labels = domain.split('.')
        if len(domain) > 253 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels):
            return text, kind, False, 'invalid-domain'
        return kind + ',' + domain, kind, True, ''
    if kind in IP_TYPES:
        if len(parts) not in (2, 3) or (len(parts) == 3 and parts[2] != 'no-resolve'):
            return text, kind, False, 'invalid-ip-options'
        try:
            net = ipaddress.ip_network(parts[1], strict=True)
            if net.version != (6 if kind == 'IP-CIDR6' else 4):
                raise ValueError('family')
        except ValueError:
            return text, kind, False, 'invalid-cidr'
        return ','.join([kind, str(net)] + parts[2:]), kind, True, ''
    return text, kind, False, 'requires-review-or-unsupported'

def extract(path, text):
    suffix = path.suffix.lower()
    if suffix == '.list':
        return 'clash-list', [(i, line.strip()) for i, line in enumerate(text.splitlines(), 1) if line.strip() and not line.lstrip().startswith(('#', ';', '//'))]
    if suffix in ('.yaml', '.yml'):
        doc = yaml.safe_load(text)
        if isinstance(doc, dict) and isinstance(doc.get('payload'), list):
            return 'provider-payload', [(i, str(value)) for i, value in enumerate(doc['payload'], 1)]
        return 'yaml-config', []
    if suffix in ('.acl', '.rule'):
        return 'acl-reference', [(i, line.strip()) for i, line in enumerate(text.splitlines(), 1) if line.strip() and not line.lstrip().startswith(('#', ';', '['))]
    return 'text-reference', []

def build(root, policy_path, output):
    lockpath = root / 'sources/acl4ssr/source-lock.json'
    lock = json.loads(lockpath.read_text(encoding='utf-8'))
    if lock.get('source_path') != '/' or lock.get('snapshot_subdir') != 'upstream':
        raise RuntimeError('Full snapshot required')
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    base = root / 'sources/acl4ssr/upstream'
    expected = {f['path'] for f in lock['files']}
    actual = {p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file() or p.is_symlink()}
    if expected != actual or len(expected) != lock['file_count']:
        raise RuntimeError('Snapshot inventory mismatch')
    inventory, records, problems, ini_refs = [], [], [], []
    source_rules = defaultdict(list)
    selected = policy['sources']
    inputs = [(f['path'], base / f['path'], f) for f in lock['files']]
    inputs += [('custom/' + p.name, p, None) for p in sorted(root.glob('*.list'))]
    inputs += [('custom/' + p.name, p, None) for p in sorted(root.glob('*.ini'))]
    for source, path, metadata in inputs:
        rel = PurePosixPath(source)
        if rel.is_absolute() or '..' in rel.parts or path.is_symlink():
            raise RuntimeError('Unsafe source path: ' + source)
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if metadata and (digest != metadata['sha256'] or len(data) != metadata['bytes']):
            raise RuntimeError('Snapshot checksum mismatch: ' + source)
        route = selected.get(source)
        row = {'source': source, 'bytes': len(data), 'sha256': digest, 'format': '', 'entries': 0, 'safe_entries': 0, 'unique_entries': 0, 'selected_category': route or ''}
        try:
            if path.suffix.lower() == '.mrs':
                fmt, items = 'binary-mrs-not-decoded', []
            else:
                text = data.decode('utf-8-sig')
                if path.suffix.lower() == '.ini':
                    ini_refs.extend({'source': source, 'line': i, 'setting': line.strip()} for i, line in enumerate(text.splitlines(), 1) if line.strip().startswith(('ruleset=', 'custom_proxy_group=')))
                if '\x00' in text:
                    fmt, items = 'binary-not-decoded', []
                else:
                    fmt, items = extract(path, text)
            row['format'] = fmt
            local = set()
            for position, raw in items:
                rule, kind, safe, reason = parse_rule(raw) if fmt in ('clash-list', 'provider-payload') else (raw, 'ACL-ENTRY', False, 'acl-not-converted')
                record = {'source': source, 'position': position, 'position_kind': 'payload-index' if fmt == 'provider-payload' else 'line', 'rule': rule, 'type': kind, 'safe_syntax': safe, 'category': route or '', 'reason': reason or ('' if route else 'unassigned-source')}
                records.append(record)
                local.add(rule)
                row['entries'] += 1
                row['safe_entries'] += int(safe)
                if route and safe and fmt == 'clash-list':
                    source_rules[rule].append({'source': source, 'position': position, 'category': route})
            row['unique_entries'] = len(local)
        except (UnicodeError, yaml.YAMLError, ValueError, TypeError) as error:
            row['format'] = 'parse-error'
            problems.append({'source': source, 'error': str(error)[:500]})
        inventory.append(row)
    missing = sorted(set(selected) - {s for s, _, _ in inputs})
    for source in missing:
        problems.append({'source': source, 'error': 'Selected source missing'})
    if any(item['source'] in selected for item in problems):
        raise RuntimeError('Selected source could not be parsed: ' + json.dumps(problems, ensure_ascii=False))
    categories = policy['categories']
    chosen, conflicts = defaultdict(list), []
    for rule, owners in sorted(source_rules.items()):
        assignments = sorted({x['category'] for x in owners}, key=lambda x: (categories[x]['priority'], x))
        winner = assignments[0]
        chosen[winner].append(rule)
        if len(assignments) > 1:
            conflicts.append({'rule': rule, 'candidate_winner': winner, 'categories': assignments, 'sources': owners})
    types = Counter(r['type'] for r in records if r['type'] != 'ACL-ENTRY')
    clash_records = [r for r in records if r['source'].startswith('Clash/') and r['source'].endswith('.list')]
    summary = {'upstream_commit': lock['commit'], 'snapshot_files': lock['file_count'], 'snapshot_bytes': lock['total_bytes'], 'audited_files': len(inventory), 'formats': dict(Counter(r['format'] for r in inventory)), 'rule_type_occurrences_all_formats': dict(sorted(types.items())), 'clash_list_occurrences': len(clash_records), 'clash_list_unique_text_rules': len({r['rule'] for r in clash_records}), 'candidate_rules': sum(map(len, chosen.values())), 'cross_category_conflicts': len(conflicts), 'parse_or_missing_issues': len(problems), 'ready_for_production': False, 'category_counts': {k: len(chosen[k]) for k in categories}, 'yaml_parser_version': yaml.__version__}
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.audit-', dir=output) as tmp:
        stage = Path(tmp)
        for name, rows, fields in [('inventory.csv', inventory, ['source','bytes','sha256','format','entries','safe_entries','unique_entries','selected_category']), ('rules.csv', records, ['source','position','position_kind','rule','type','safe_syntax','category','reason'])]:
            with (stage / name).open('w', encoding='utf-8-sig', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        for name, obj in [('summary.json', summary), ('conflicts.json', conflicts), ('parse-issues.json', problems), ('provenance.json', source_rules), ('ini-references.json', ini_refs)]:
            (stage / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        lines = ['# ACL4SSR 正文解析与业务候选', '', '状态：待人工审核，不可直接部署。', '', '- 上游提交：`' + lock['commit'] + '`', '- 快照文件：' + str(lock['file_count']), '- 审核文件（含根目录自建列表）：' + str(len(inventory)), '- 候选规则：' + str(summary['candidate_rules']), '- 跨业务精确冲突：' + str(len(conflicts)), '- 解析/缺失问题：' + str(len(problems)), '', '| 业务 | 默认节点 | 候选条数 |', '|---|---|---:|']
        lists = stage / 'rules'
        lists.mkdir()
        for category, definition in sorted(categories.items(), key=lambda pair: pair[1]['priority']):
            values = sorted(chosen[category])
            (lists / (category + '.list')).write_text('# REVIEW ONLY; not referenced by active INI\n' + '\n'.join(values) + '\n', encoding='utf-8')
            lines.append('| ' + category + ' | ' + definition['node'] + ' | ' + str(len(values)) + ' |')
        lines += ['', '## 统计边界', '', '- Providers 与 .list 分开识别；候选仅从明确选择的 .list 生成，避免多格式重复导入。', '- ACL 只登记参考条目，MRS/二进制只做校验与资产登记，未解码。其他文本仅登记资产，不声称解析其业务语义。', '- 关键词、进程、URL 正则、复杂/未知类型不进入候选；详见 rules.csv。', '- 精确冲突按策略优先级给出候选归属，同时完整保留 conflicts.json；这不是冲突已解决。', '- 未执行完整父域/关键词遮蔽分析、IP 重叠分析或实际服务验收。候选文件无跨文件匹配顺序，不构成可部署配置。', '- 自建 MediaHK/英美台等混合或未具备对应出口的来源默认待审，不按原标签全量迁移。', '- 未修改 INI 或生产规则；不会自动上传或部署候选。']
        (stage / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        (stage / 'policy-used.json').write_text(json.dumps(policy, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for entry in stage.iterdir():
            destination = output / entry.name
            if destination.exists():
                shutil.rmtree(destination) if destination.is_dir() else destination.unlink()
            shutil.move(str(entry), destination)
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.root.resolve(), args.policy.resolve(), args.output.resolve())
