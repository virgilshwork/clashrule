#!/usr/bin/env python3
"""Snapshot the full upstream Git tree without executing upstream code."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = 'https://github.com/ACL4SSR/ACL4SSR.git'
DEST = ROOT / 'sources' / 'acl4ssr'

def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ref', default='master')
    args = parser.parse_args()
    if args.ref != 'master' and not re.fullmatch(r'[0-9a-fA-F]{40}', args.ref):
        parser.error('--ref must be master or a full commit SHA')
    if DEST.parent.is_symlink() or DEST.is_symlink():
        raise RuntimeError('Refusing symlink destination or parent')
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        lockpath = DEST / 'source-lock.json'
        if lockpath.is_symlink() or not lockpath.is_file():
            raise RuntimeError('Existing destination is not a managed snapshot')
        old = json.loads(lockpath.read_text(encoding='utf-8'))
        if old.get('repository') != UPSTREAM or not isinstance(old.get('files'), list):
            raise RuntimeError('Unrecognized snapshot manifest')
    with tempfile.TemporaryDirectory(prefix='acl4ssr-fetch-') as tmp:
        repo = Path(tmp) / 'upstream'
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        subprocess.run(['git', '-C', str(repo), 'remote', 'add', 'origin', UPSTREAM], check=True)
        subprocess.run(['git', '-C', str(repo), 'fetch', '--depth=1', 'origin', args.ref], check=True)
        commit = git(repo, 'rev-parse', 'FETCH_HEAD^{commit}').decode().strip()
        records = git(repo, 'ls-tree', '-r', '-z', commit).split(b'\0')
        entries = []
        unsupported = []
        for record in filter(None, records):
            header, rawpath = record.split(b'\t', 1)
            mode, kind, oid = header.decode('ascii').split()
            name = rawpath.decode('utf-8')
            relative = PurePosixPath(name)
            if relative.is_absolute() or any(p in ('..', '.git') for p in relative.parts):
                raise RuntimeError('Unsafe upstream path: ' + name)
            if kind != 'blob' or mode not in ('100644', '100755'):
                unsupported.append({'path': name, 'mode': mode, 'type': kind})
            else:
                entries.append((name, mode, oid))
        if unsupported:
            raise RuntimeError('Unsupported links/submodules; old snapshot unchanged: ' + json.dumps(unsupported, ensure_ascii=False))
        if not entries:
            raise RuntimeError('Empty upstream tree; refusing replacement')
        with tempfile.TemporaryDirectory(prefix='.acl4ssr-stage-', dir=DEST.parent) as tmpstage:
            stage = Path(tmpstage) / 'snapshot'
            stage.mkdir()
            manifest = []
            for name, mode, oid in sorted(entries):
                data = git(repo, 'cat-file', 'blob', oid)
                if len(data) > 100_000_000:
                    raise RuntimeError('Oversized file; review storage policy: ' + name)
                target = stage / 'upstream' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                target.chmod(0o755 if mode == '100755' else 0o644)
                manifest.append({'path': name, 'mode': mode, 'type': 'blob', 'git_oid': oid, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            lock = {'schema_version': 2, 'repository': UPSTREAM, 'commit': commit, 'source_path': '/', 'snapshot_subdir': 'upstream', 'file_count': len(manifest), 'total_bytes': sum(f['bytes'] for f in manifest), 'files': manifest}
            (stage / 'source-lock.json').write_text(json.dumps(lock, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            backup = Path(tmpstage) / 'previous'
            if DEST.exists():
                os.replace(DEST, backup)
            try:
                os.replace(stage, DEST)
            except BaseException:
                if backup.exists():
                    os.replace(backup, DEST)
                raise
            if backup.exists():
                shutil.rmtree(backup)
            print(json.dumps({'commit': commit, 'files': len(manifest), 'bytes': lock['total_bytes'], 'destination': str(DEST.relative_to(ROOT))}))

if __name__ == '__main__':
    main()
