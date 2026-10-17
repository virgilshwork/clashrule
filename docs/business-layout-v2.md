# 按业务组织的候选规则 v2

工作流名称仍为 Audit ACL4SSR and Build Draft Rules。运行成功后下载 acl4ssr-business-v2 开头的附件。旧附件不会被覆盖，请按运行提交和时间识别版本。脚本/策略推送、同步成功后以及手动触发均保留。

## 三层分离

rules/*.list 按业务命名，不按节点/出口地区命名。business-plan.json 单独记录业务到默认角色的映射；角色到节点的对应在 roles 中；地区要求/避开地区在 proposed_constraints 中。地区约束是拟定策略，不是逐站验证结论。GGC A/B 只出现在 standby_only，不作日常默认。

OpenAI/Anthropic、其他 AI、GitHub 网页/API、GitHub 下载、海外下载、YouTube、其他视频、Netflix、Spotify、成人内容、微软、云同步、电报、加密货币、挖矿、苹果商店、游戏、共享依赖等独立输出。mytvsuper/viutv/dmm/abematv/hulu_japan 是服务身份，不是将普通海外按地区聚合。

成人内容默认东京、按运营策略避开韩国，但没有必须日本的约束。DMM 等另有拟定日本约束。其他 AI 暂沿用大阪候选，核心交互仅由显式规则种子选取 api.github.com、api.githubcopilot.com、perplexity.ai；可编辑 rule_overrides 调整。AI_other 中已列出的共享登录、支付、遥测主机单独归 shared_services，跨来源冲突仍记录。

## 生成与审核

保留原审计器与 business-draft.json 作为输入种子，新 business-layout.json 覆盖业务归属并解耦出口。最终以 business-plan.json、REPORT.md、summary.json、rules/*.list 为准。policy-used.json 是中间编译配置；layout-used.json 保存本次新结构。

旧 MediaHK/MediaJPN/英美台/Amazon 的混合条目不能仅凭旧标签搬迁；这些来源中的精确同名通用候选会暂缓，见 pending-business-review.json。父域间接覆盖尚未解除，不能因此认定所有旧域名都不再进入通用业务。

新增 OneDrive 为 cloud_sync 候选，不代表所有同步都应代理；gaming_download 当前是空模板，待区分国内直连与海外传输后补齐。Netflix、Pixiv 等候选不意味着账号、地区或播放功能通过。

keywords/process/URL-regex 等保留审计记录，不进入候选；MRS 未解码。当前只做语法与精确冲突处理，不做完整父域遮蔽、IP 重叠或全局匹配顺序。始终 ready_for_production=false。禁止直接按列表文件顺序上线。

inventory.csv 的 selected_category 是初始来源分类；最终业务覆盖见 rules.csv/provenance.json。修改 role 不改变业务文件名。已有根目录业务列表、INI、来源快照、每天北京时间 06:00 同步计划均不修改。产物只作为 Actions 附件，30 天保留，不自动提交或部署。

本地运行：python scripts/build_business_rules.py --seed policy/business-draft.json --layout policy/business-layout.json --output business-output。需 Python 3.12、PyYAML 6.0.2；输出目录必须不存在。
