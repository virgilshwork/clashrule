# 节点角色与核心 AI 口径

## 业务与出口独立

取消 core_interactive 分类，不再生成额外的 core_interactive.list。核心出口 core_exit 仍保留；业务归属不等于必须使用不同节点。

- github_web_api：GitHub 网页、登录与 API，包含 api.github.com，默认 core_exit -> OSAKA_Premium。
- ai_other：OpenAI / Anthropic 之外的其他 AI 交互，包含 Copilot 与 Perplexity，默认 core_exit -> OSAKA_Premium。
- openai_anthropic：独立默认 general_exit -> KR_Evoxt，本次不改。
- github_bulk：已确认的独立下载端点，默认 capacity_exit -> TOKYO_Standby。

Copilot 的 api.githubcopilot.com、githubcopilot.com 后缀及 copilot-proxy.githubusercontent.com 明确归 AI，不因为 githubusercontent.com 的宽泛分类而认定是下载。当前生成器的 rule_overrides 只对实际解析到的对应规则生效，不凭空新增缺失主机；实际覆盖和精确例外优先级须在后续验收。

同一 github.com HTTPS 主机上的登录、网页、Git 传输等不能仅靠当前域名规则按 URL 路径拆分；通过该主机的部分传输可能仍消耗大阪。下载分流仅承诺已明确分类的独立下载主机，不声称按所有下载行为准确识别。

## 日本与容量角色分离

jp_exit 默认 TOKYO_Standby，供 DMM、AbemaTV、Hulu Japan、Niconico 使用；capacity_exit 默认同一节点但逻辑独立，服务于下载和同步。业务是否必须日本由独立约束表达；Niconico 仅为当前出口偏好。

## 审核边界

ai_other 以现有 AI_other.list 为来源，不代表穷尽全部 AI。共享依赖拆分与关键词暂缓未变，候选不等价于旧列表全部行为。旧附件不会删除，应验收最新运行。此次仅修改候选生成策略与说明，不改生产 INI、运行时选择或每日同步计划。
