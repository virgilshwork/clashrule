# ACL4SSR 全仓库来源快照

## 范围与布局

上游：https://github.com/ACL4SSR/ACL4SSR.git

同步指定提交的全部普通受版本管理文件到 `sources/acl4ssr/upstream/`，保留相对路径、原始字节与可执行模式。不复制 Git 历史、分支或 `.git`；不执行上游代码。上游工作流仅保存在嵌套来源目录，不写入本仓库根工作流目录。Git LFS 指针按 Git blob 保存，不额外下载 LFS 对象。

`source-lock.json` 位于 `sources/acl4ssr/`，记录 schema、上游提交、路径、模式、Git blob ID、大小、SHA-256 与总量。无时间戳，相同快照可重复生成。完整快照是来源资料，不代表全部内容已审核或应加载。

## 运行

GitHub Actions 工作流名为 `Sync ACL4SSR Repository`；北京时间每天 06:00（UTC 22:00）计划运行，同时保留手动触发。调度可能延迟。工作流文件路径仍为 `.github/workflows/sync-acl4ssr.yml`。main 应为默认分支，Actions 必须启用并允许内容写入。

手动运行时选择 main，输入 master 或完整 40 位提交 SHA。本地运行：

```sh
python3 scripts/sync_acl4ssr.py --ref master
git diff --stat
git diff -- sources/acl4ssr/source-lock.json
```

本地脚本不提交或推送。Actions 只提交 `sources/acl4ssr/`；不修改业务列表、INI、节点或生产配置。无变化不创建空提交。仅上游提交变化也可能更新清单并产生提交。

## 局部快照迁移

首次全量运行会替换托管的 `sources/acl4ssr/`，将旧 `Clash/Ruleset/` 内容迁至 `upstream/Clash/Ruleset/`，并补齐其他上游文件。清单继续使用上游相对路径，摘要会标记范围扩展，不将文件搬迁当成上游新增。不要在托管目录保存人工修改；这些内容会在同步时被替换。

## 安全边界

下载及新文件树生成成功后再替换旧快照。替换时先重命名旧目录，正常异常时尝试恢复；这不是跨系统崩溃事务，意外中断后可通过 Git 恢复。符号链接、子模块或特殊树条目会在替换前拒绝并列出，不能声称已同步它们。单文件超过 100,000,000 字节也拒绝，需要单独设计存储策略。保留上游许可与说明，后续再分发应审核适用许可。

## 摘要与回滚

Actions Summary 显示北京时间、触发方式、步骤结果、旧新版本、文件数和字节数，分别统计全仓库、Clash、Clash/Ruleset 的新增/修改/删除，列出最多 300 项变化与成功推送的提交链接。修改按内容或模式变化判断，不是有效规则条数统计。迁移或首次同步的新增不等同于上游新建。

推送失败时摘要会标注工作区差异未发布；不会强推绕过分支保护或并发更新。检查日志后重跑。通过正常 Git revert 回退快照提交；若也要回退同步机制，需另外回退脚本/工作流改造提交。首次全量同步和摘要须以实际 Actions 运行结果验收，安装工作流本身不触发同步。
