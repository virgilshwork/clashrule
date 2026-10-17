# 候选 SubConverter INI

以仓库 virgil-v2.ini 的 [custom]、ruleset、custom_proxy_group 和生成器开关为格式基础。新增脚本 generate_candidate_ini.py 消费同一轮业务附件，生成 virgil-candidate.ini 与 ini-validation.json；不覆盖原 INI。

## 不依赖不存在的规则 URL

候选列表尚未发布为可拉取的仓库文件，因此每条候选以 ruleset=业务组,[]规则 内嵌，不引用虚构 raw 地址。INI 是来源快照与分类策略的固定结果；重新运行流程才更新其内容。大小可能明显大于旧 INI，需要实际转换器验证规则/配置大小限制。

## 映射与手动备用

业务规则文件名不变，独立业务组的首选引用逻辑角色。GitHub 交互与其他 AI 引用同一个大阪核心角色；OpenAI/Anthropic、普通海外和视频引用韩国普通角色；下载/同步引用东京容量角色；香港限定引用 Evoxt 香港；日本专项引用独立 jp_exit（东京）。

六个节点组精确匹配固定节点名，并保留 REJECT 候选以避免空角色无声直连。逻辑角色组只有默认节点组与 REJECT，不自动测速或故障切换。业务组可在地区约束允许时手动选择 GGC A/B；GGC A 已知故障未由此修复，启用前必须验证。默认不选任何 GGC。旧 Selector 缓存可能覆盖首选，必须检查生成 YAML 的成员与运行时选择。

## 候选顺序

本版提出全局排序：所有域名规则在 IP 前；子域比父域靠前；相同深度的 DOMAIN 先于 DOMAIN-SUFFIX；业务优先级用于打破特异性相同的平局。IP 按前缀长度降序。最后 GEOIP,CN 直连、FINAL 普通海外。不再按 31 个文件粗略拼接，避免 GitHub 父域提前覆盖下载子域。

这会改变部分旧优先级，尚未完成所有父域、IP 与局域网/DNS场景验收。七项离线域名首匹配断言覆盖 github.com、api.github.com、api.githubcopilot.com、copilot-proxy.githubusercontent.com、perplexity.ai、codeload.github.com、release-assets.githubusercontent.com。断言失败停止且不上传成功附件。

## 获取与验收

工作流名不变，成功附件改为 acl4ssr-business-ini 开头，内含规则、审计报告、INI 与验证记录。脚本变更推送、同步成功后、手动运行均可触发。此前附件保留，不代表最新版。

生成检查只验证候选计数、去重、组名与组引用、配置声明的地区约束、七项域名顺序及交互默认节点一致。不包含实际 SubConverter 转换、mihomo -t、DNS/IP 路由、真实出口、登录/Copilot 补全或持续下载验收。ready_for_production 仍为 false，不应直接替换生产。

必须先完成：审查 conflicts/pending/parse-issues，使用实际转换服务生成 YAML，检查六个真实节点是否存在和组默认值，执行 mihomo 配置检查，在测试配置中验证登录、Copilot、下载与国内直连；失败回到原配置。overwrite_original_rules=true 沿用旧文件，请确认没有必须保留的订阅原始私有规则。

本地运行：python scripts/generate_candidate_ini.py --input business-output。需要同目录下现有审计模块及 PyYAML 6.0.2。初始自动运行是否成功以 Actions 为准，提交代码不等于已经生成真实快照的 INI。
