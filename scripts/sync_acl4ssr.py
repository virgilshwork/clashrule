#!/usr/bin/env python3
"""Mirror ACL4SSR Ruleset bytes at a resolved commit; never edit active rules."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = 'https://github.com/ACL4SSR/ACL4SSR.git'
PREFIX = 'Clash/Ruleset/'
DEST = ROOT / 'sources' / 'acl4ssr'

def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ref', default='master', help='master or a full 40-character commit SHA')
    args = parser.parse_args()
    if args.ref != 'master' and not re.fullmatch(r'[0-9a-fA-F]{40}', args.ref):
        parser.error('--ref must be master or a full commit SHA')
    if DEST.is_symlink():
        raise RuntimeError('Refusing symlink destination')
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists() and not (DEST / 'source-lock.json').is_file():
        raise RuntimeError('Existing destination is not a managed snapshot')
    with tempfile.TemporaryDirectory(prefix='acl4ssr-fetch-') as tmp:
        repo = Path(tmp) / 'upstream'
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        subprocess.run(['git', '-C', str(repo), 'remote', 'add', 'origin', UPSTREAM], check=True)
        subprocess.run(['git', '-C', str(repo), 'fetch', '--depth=1', 'origin', args.ref], check=True)
        commit = git(repo, 'rev-parse', 'FETCH_HEAD^{commit}').decode().strip()
        paths = git(repo, 'ls-tree', '-r', '-z', '--name-only', commit, '--', PREFIX).split(b'\0')
        paths = sorted(p.decode('utf-8') for p in paths if p)
        if not paths:
            raise RuntimeError('Upstream Ruleset is empty; refusing replacement')
        with tempfile.TemporaryDirectory(prefix='.acl4ssr-stage-', dir=DEST.parent) as staging:
            stage = Path(staging)
            manifest = []
            for name in paths:
                relative = Path(name)
                if not name.startswith(PREFIX) or relative.is_absolute() or '..' in relative.parts:
                    raise RuntimeError('Unsafe upstream path: ' + name)
                mode = git(repo, 'ls-tree', commit, '--', name).split(None, 1)[0]
                if mode not in (b'100644', b'100755'):
                    raise RuntimeError('Unsupported upstream entry: ' + name)
                data = git(repo, 'show', commit + ':' + name)
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                manifest.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            lock = {'repository': UPSTREAM, 'commit': commit, 'source_path': PREFIX, 'file_count': len(manifest), 'files': manifest}
            (stage / 'source-lock.json').write_text(json.dumps(lock, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            if DEST.exists():
                shutil.rmtree(DEST)
            shutil.copytree(stage, DEST)
            print(json.dumps({'commit': commit, 'files': len(manifest), 'destination': str(DEST.relative_to(ROOT))}))

if __name__ == '__main__':
    main()
