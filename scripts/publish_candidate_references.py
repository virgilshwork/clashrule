#!/usr/bin/env python3
"""Publish review-only reference INI and immutable candidate rule snapshots."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from generate_candidate_ini import emit, BUSINESS_NAMES

RAW = 'https://raw.githubusercontent.com/virgilshwork/clashrule/main/candidates/snapshots/'

def publish(folder, destination):
    emit(folder)
    inline = (folder / 'virgil-candidate.ini').read_text(encoding='utf-8')
    plan = json.loads((folder / 'business-plan.json').read_text(encoding='utf-8'))
    reverse = {label: name for name, label in BUSINESS_NAMES.items()}
    blocks, current, original = [], None, []
    retained = []
    for line in inline.splitlines():
        if line.startswith('ruleset='):
            target, value = line.split('=', 1)[1].split(',', 1)
            if value in ('[]GEOIP,CN', '[]FINAL'):
                retained.append(line)
                continue
            if not value.startswith('[]'):
                raise RuntimeError('Unexpected source INI rule')
            business = reverse[target]
            rule = value[2:]
            original.append((target, rule))
            if current is None or current['business'] != business:
                current = {'business': business, 'target': target, 'rules': []}
                blocks.append(current)
            current['rules'].append(rule)
    if len(retained) != 2:
        raise RuntimeError('Expected exactly GEOIP and FINAL tail rules')
    digest = hashlib.sha256(b'reference-publication-v1\n' + inline.encode())
    business_files = {}
    for business, definition in sorted(plan['businesses'].items()):
        if not re.fullmatch(r'[a-z0-9_]+', business):
            raise RuntimeError('Unsafe business name')
        path = folder / definition['file']
        data = path.read_bytes()
        business_files['rules/' + business + '.list'] = data
        digest.update(business.encode() + b'\0' + data)
    digest.update(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode())
    version = digest.hexdigest()
    payload = dict(business_files)
    references, reconstructed, entries = [], [], []
    for index, block in enumerate(blocks, 1):
        path = 'rules/ordered/' + str(index).zfill(5) + '-' + block['business'] + '.list'
        data = ('# Ordered fragment; review only; business=' + block['business'] + '\n' + '\n'.join(block['rules']) + '\n').encode()
        payload[path] = data
        references.append('ruleset=' + block['target'] + ',' + RAW + version + '/' + path)
        reconstructed.extend((block['target'], rule) for rule in block['rules'])
        entries.append({'path': path, 'business': block['business'], 'rules': len(block['rules']), 'sha256': hashlib.sha256(data).hexdigest()})
    if reconstructed != original:
        raise RuntimeError('Reference fragments changed rule ordering')
    groups_and_switches = [line for line in inline.splitlines() if line.startswith(('custom_proxy_group=', 'enable_rule_generator=', 'overwrite_original_rules='))]
    lines = ['[custom]', '; Reference-only candidate configuration; NOT production-approved.', '; Business identity, role selection and regional constraints remain separate.', '; Snapshot: ' + version, '; Rules are remote list references; only GEOIP/CN and FINAL are inline.', '; Ordered fragments preserve the exact sequence validated by the existing generator.', '; GGC choices are manual standby only; no automatic failover.', '; Verify node names, selector cache, actual conversion and business behavior before use.', '']
    lines += references + retained + ['', '; Node, role and business group definitions.'] + groups_and_switches + ['']
    content = '\n'.join(lines).encode('utf-8')
    if any(line.startswith('ruleset=') and ',[]' in line and line not in retained for line in content.decode().splitlines()):
        raise RuntimeError('Business rules still inline')
    payload['virgil-candidate.ini'] = content
    payload['business-plan.json'] = (folder / 'business-plan.json').read_bytes()
    validation = json.loads((folder / 'ini-validation.json').read_text(encoding='utf-8'))
    validation.update({'ini_mode': 'remote-references', 'ini_sha256': hashlib.sha256(content).hexdigest(), 'publication_id': version, 'ordered_fragments': len(blocks), 'order_preserved': True, 'remote_files_published': 'not-confirmed-until-workflow-push'})
    payload['ini-validation.json'] = (json.dumps(validation, ensure_ascii=False, indent=2) + '\n').encode()
    manifest = {'managed_by': 'clashrule-reference-publisher-v1', 'publication_id': version, 'ready_for_production': False, 'ordered_fragments': entries, 'files': [{'path': path, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for path, data in sorted(payload.items())]}
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    payload['manifest.json'] = manifest_bytes
    if destination.is_symlink():
        raise RuntimeError('Refusing symlink publication root')
    marker = destination / 'manifest.json'
    if destination.exists():
        if not marker.is_file() or marker.is_symlink() or json.loads(marker.read_text()).get('managed_by') != manifest['managed_by']:
            raise RuntimeError('Existing publication root is not managed; refusing overwrite')
    snapshot = destination / 'snapshots' / version
    if snapshot.exists():
        actual = {p.relative_to(snapshot).as_posix() for p in snapshot.rglob('*') if p.is_file() or p.is_symlink()}
        if actual != set(payload):
            raise RuntimeError('Immutable snapshot inventory mismatch')
        for path, data in payload.items():
            target = snapshot / path
            if target.is_symlink() or target.read_bytes() != data:
                raise RuntimeError('Immutable snapshot content mismatch: ' + path)
    else:
        for path, data in payload.items():
            target = snapshot / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'virgil-candidate.ini').write_bytes(content)
    marker.write_bytes(manifest_bytes)
    (folder / 'virgil-candidate.ini').write_bytes(content)
    (folder / 'ini-validation.json').write_bytes(payload['ini-validation.json'])
    (folder / 'reference-manifest.json').write_bytes(manifest_bytes)
    fragments = folder / 'reference-rule-parts'
    if fragments.exists():
        shutil.rmtree(fragments)
    fragments.mkdir()
    for entry in entries:
        (fragments / Path(entry['path']).name).write_bytes(payload[entry['path']])
    report = folder / 'REPORT.md'
    report.write_text(report.read_text(encoding='utf-8').split('\n## 候选 INI\n', 1)[0] + '\n## 引用式候选 INI\n\n业务规则不再内嵌。发布版本：`' + version + '`。有序引用片段：' + str(len(blocks)) + '；原业务列表仍保留。顺序重建校验通过；是否已推送须看发布步骤结果。ready_for_production=false。\n', encoding='utf-8')
    print(json.dumps({'publication_id': version, 'business_lists': len(business_files), 'ordered_fragments': len(blocks), 'ready_for_production': False}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--publish-root', type=Path, required=True)
    args = parser.parse_args()
    publish(args.input.resolve(), args.publish_root.absolute())
