#!/usr/bin/env python3
"""Write an Actions summary from the old and newly generated manifests."""
import html
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

def esc(value):
    return html.escape(str(value)).replace('|', '&#124;').replace('\n', ' ')

def code(value):
    return '<code>' + esc(value) + '</code>'

def main():
    env = os.environ
    fetch = env.get('FETCH_RESULT', '')
    publish = env.get('PUBLISH_RESULT', '')
    status = '失败或未完成'
    if fetch == 'success' and publish == 'success':
        status = '成功：已推送更新' if env.get('SNAPSHOT_CHANGED') == 'true' else '成功：无变化'
    lines = ['## ACL4SSR 全仓库同步摘要', '', '| 项目 | 结果 |', '|---|---|']
    rows = [('摘要时间（北京时间）', datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')), ('触发方式', env.get('GITHUB_EVENT_NAME', '')), ('请求版本', env.get('UPSTREAM_REF', '')), ('结果', status), ('抓取步骤', fetch or '未运行'), ('发布步骤', publish or '未运行')]
    lines += ['| ' + esc(k) + ' | ' + esc(v) + ' |' for k, v in rows]
    try:
        base = env.get('BASE_SHA', '')
        if not base or fetch != 'success':
            lines += ['', '没有可确认的新快照，不输出差异结论；请检查原始日志。']
        else:
            lockpath = 'sources/acl4ssr/source-lock.json'
            old = {}
            result = subprocess.run(['git', 'show', base + ':' + lockpath], capture_output=True, text=True)
            if result.returncode == 0:
                old = json.loads(result.stdout)
            else:
                check = subprocess.run(['git', 'ls-tree', '--name-only', base, '--', lockpath], capture_output=True, text=True, check=True)
                if check.stdout.strip():
                    raise RuntimeError('Cannot read baseline manifest')
            new = json.loads(Path(lockpath).read_text(encoding='utf-8'))
            before = {f['path']: (f['sha256'], f.get('mode', '100644')) for f in old.get('files', [])}
            after = {f['path']: (f['sha256'], f.get('mode', '100644')) for f in new['files']}
            added = sorted(after.keys() - before.keys())
            deleted = sorted(before.keys() - after.keys())
            modified = sorted(p for p in before.keys() & after.keys() if before[p] != after[p])
            migration = bool(old) and old.get('source_path') != '/'
            lines += ['', '### 快照版本', '', '- 旧提交：' + code(old.get('commit', '无（首次同步）')), '- 新提交：' + code(new['commit']), '- 新快照文件数：' + str(len(after)), '- 新快照字节数：' + str(new.get('total_bytes', sum(f['bytes'] for f in new['files']))), '- 存储目录：' + code('sources/acl4ssr/upstream/')]
            if migration:
                lines += ['', '本轮为局部快照到全量快照的范围迁移。新增中包含此前未同步的文件，不代表上游本次新建了这些文件；文件搬迁不计为上游删除/新增。']
            lines += ['', '### 文件变化', '', '| 范围 | 新增 | 修改 | 删除 |', '|---|---:|---:|---:|']
            for label, prefix in [('全仓库', ''), ('Clash 全目录', 'Clash/'), ('Clash/Ruleset', 'Clash/Ruleset/')]:
                counts = [sum(p.startswith(prefix) for p in group) for group in (added, modified, deleted)]
                lines.append('| ' + label + ' | ' + ' | '.join(map(str, counts)) + ' |')
            only_version = bool(old) and not migration and old.get('commit') != new['commit'] and not (added or modified or deleted)
            lines += ['', '- 仅上游版本变化：' + ('是' if only_version else '否'), '', '统计以清单内上游相对路径为准，不含来源清单本身；修改包括字节或 Git 文件模式变化，不等于有效规则数量变化。']
            entries = [('新增', p) for p in added] + [('修改', p) for p in modified] + [('删除', p) for p in deleted]
            if entries:
                lines += ['', '### 变更清单（最多 300 项）', '', '| 类型 | 上游路径 |', '|---|---|']
                lines += ['| ' + kind + ' | ' + code(path) + ' |' for kind, path in entries[:300]]
                if len(entries) > 300:
                    lines += ['', '剩余变化请查看快照提交和完整 source-lock.json。']
            sha = env.get('PUBLISHED_SHA', '')
            if sha:
                url = env['GITHUB_SERVER_URL'] + '/' + env['GITHUB_REPOSITORY'] + '/commit/' + sha
                lines += ['', '快照提交：[' + sha + '](' + url + ')']
            elif publish != 'success':
                lines += ['', '未确认推送成功；上述差异仅描述工作区，不代表 main 已更新。']
        lines += ['', '来源快照不等于生产规则；不会执行上游代码或修改业务 INI。失败详情见步骤日志。']
    except Exception as error:
        lines += ['', '摘要统计失败：' + code(error)]
        with open(env['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as out:
            out.write('\n'.join(lines) + '\n')
        raise
    with open(env['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as out:
        out.write('\n'.join(lines) + '\n')

if __name__ == '__main__':
    main()
