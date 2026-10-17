# 按业务组织的候选规则 v2

工作流 Audit ACL4SSR and Build Draft Rules 成功后生成 acl4ssr-business-v2 开头的附件。按提交和时间识别新旧版本。保留推送触发、成功同步后触发和手动运行。

## 分类、角色与约束

rules/*.list 按业务命名；business-plan.json 将业务映射到角色，roles 将角色映射到节点，proposed_constraints 保存拟定地区约束。约束不是逐站实测结论。GGC A/B 仅作为 standby_only。

取消 core_interactive，共 31 个业务文件（可能为空）。GitHub 网页/登录/API 归 github_web_api；Copilot、Perplexity 归 ai_other。两类业务都选择 core_exit -> OSAKA_Premium，避免把业务拆分误解为出口必须分开。OpenAI/Anthropic 仍独立走韩国。

GitHub 独立下载端点归 github_bulk -> capacity_exit -> TOKYO_Standby。Copilot 的 api.githubcopilot.com、githubcopilot.com 后缀与 copilot-proxy.githubusercontent.com 保留 AI 归属；rule_overrides 对已经解析到的规则生效，不能代替覆盖检查。精确下载主机须优先于 GitHub 宽泛后缀，Copilot 例外也须优先于任何覆盖它的宽泛下载规则。当前未生成全局加载顺序，因此仍不可直接上线。

同一 github.com 主机的 HTTPS 路径不由本域名分类器拆分，一部分 Git/下载传输仍可能走大阪。源 Download.list 也不等同于海外下载。

DMM/AbemaTV/Hulu Japan/Niconico 使用 jp_exit；下载、同步与成人内容使用 capacity_exit。两者当前都为东京，逻辑独立。adult_content 按策略避开韩国，但不要求必须日本。Niconico 不新增必须日本约束。

## 来源与审核

business-draft.json 是来源种子，business-layout.json 决定新布局。policy-used.json 是中间编译配置，layout-used.json 是本轮布局。最终归属见 rules.csv/provenance.json，inventory.csv 的 selected_category 仅代表初始来源分类。

旧混合地区列表保留待审，精确同名的通用候选可暂缓，见 pending-business-review.json；父域间接覆盖尚未消除。OneDrive/cloud_sync 是否代理须验收，gaming_download 仍为空模板。候选不证明 Netflix 等业务的地区与账号功能正常。

关键词、进程、URL 正则等保留审核记录但不进入候选，MRS 未解码。未完成父域遮蔽、IP 重叠或全局顺序分析，ready_for_production=false。产物仅作为 30 天 Actions 附件，不自动提交或部署，不修改根目录规则、生产 INI、运行时选择或北京时间 06:00 来源同步计划。

本地：python scripts/build_business_rules.py --seed policy/business-draft.json --layout policy/business-layout.json --output business-output。需 Python 3.12、PyYAML 6.0.2；输出目录必须不存在。
