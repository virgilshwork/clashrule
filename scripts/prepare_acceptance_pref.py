#!/usr/bin/env python3
"""Initialize and validate preferences inside an isolated SubConverter work copy."""
import argparse
from pathlib import Path
import re
import tomllib


def prepare(directory):
    pref = directory / 'pref.toml'
    source = pref if pref.is_file() else directory / 'pref.example.toml'
    if not source.is_file():
        names = sorted(p.name for p in directory.iterdir() if p.is_file() and p.suffix in ('.toml', '.ini', '.yml'))
        raise RuntimeError('Neither pref.toml nor pref.example.toml exists; configuration files: ' + repr(names))
    text = source.read_text(encoding='utf-8')
    tomllib.loads(text)
    for key, value in [('api_mode', 'false'), ('max_allowed_rulesets', '512')]:
        text, count = re.subn(r'(?m)^' + re.escape(key) + r'\s*=.*$', key + ' = ' + value, text)
        if count != 1:
            raise RuntimeError('Expected one active setting for ' + key + ', found ' + str(count))
    parsed = tomllib.loads(text)
    if parsed.get('common', {}).get('api_mode') is not False:
        raise RuntimeError('common.api_mode was not configured correctly')
    if parsed.get('advanced', {}).get('max_allowed_rulesets') != 512:
        raise RuntimeError('advanced.max_allowed_rulesets was not configured correctly')
    pref.write_text(text, encoding='utf-8')
    return {'source': source.name, 'target': pref.name, 'api_mode': False, 'max_allowed_rulesets': 512}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print(prepare(args.directory.resolve()))
