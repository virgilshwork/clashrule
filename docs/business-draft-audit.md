# 全量来源正文审计与业务候选

本流程不修改生产 INI、根目录业务列表或运行时选择，不自动部署候选。

## 执行

工作流 `Audit ACL4SSR and Build Draft Rules`：可手动触发；审计脚本/策略/工作流在 main 修改时触发；全仓库同步工作流成功且来源分支为 main 后也触发。读取执行时 main 的快照，在日志记录输入提交。首次安装是否触发以 Actions 实际记录为准；未自动触发可手动运行。

## 全文件口径

逐个校验 source-lock.json 中的全部文件，核对目录清单、字节数和 SHA-256；再登记根目录自建 .list 与 INI。Clash .list 逐行解析，YAML 使用 safe_load，payload 记录索引。ACL 仅按非注释条目登记，不转换为 Clash。MRS 和二进制仅资产登记与校验，未解码。其他文本登记来源；INI 提取 ruleset/custom_proxy_group 引用。不能把这称为全部格式均已完成语义解析。

只有被 policy/business-draft.json 明确选中的 .list 中，经过保守语法校验的 DOMAIN、DOMAIN-SUFFIX、IP-CIDR、IP-CIDR6 才进入候选。关键词、URL 正则、进程、未知/复杂规则全部保留在审计记录但不生成候选；Providers 不重复导入。注释内数量不作为统计来源。

## 初始策略

大阪核心，韩国普通海外/视频/独立 AI，Evoxt 香港地区专项，东京下载/日本及非韩国专项，GGC 不作日常默认。来源分类是待审候选，不是已证明每个域名需要该地区。现有混合 MediaHK、英/美/台、Amazon、OneDrive/GameDownload 等不自动整组搬迁。AppleStore 作为普通海外候选。现有 AI_other 暂作为核心兼容种子，需逐条审查是否值得占用大阪。

精确冲突按数字优先级给出候选胜者并完整记录；没有完成父域遮蔽、IP 重叠、跨组顺序或服务可用性验收。候选列表不能按文件名直接拼接上线；summary.json 始终标记 ready_for_production=false。安全语法校验也不是 mihomo 引擎完整校验。

## 输出

Actions Summary 显示总体报告。运行成功后生成 30 天保留的 artifact，包含 inventory.csv、rules.csv、summary.json、conflicts.json、parse-issues.json、provenance.json、ini-references.json、policy-used.json、REPORT.md 与 rules/*.list。全格式出现次数可能重复；Clash .list 统计单列。文件内冗余可由 inventory 的 entries/unique_entries 对比，跨来源关系见 rules/provenance；精确文本去重不等于语义去重。

校验失败、选中来源缺失或无法解析时停止，不上传成功候选；未选中来源的解析错误仍列入问题报告，必须审核，不能当作零错误。未读取的真实请求与出口不能由本报告推断。

本地：Python 3.12、PyYAML 6.0.2，运行 `python scripts/audit_acl4ssr.py --policy policy/business-draft.json --output draft-output`。不要将 output 指向现有业务规则目录。
