# 节点角色与核心 AI 口径

## 日本与容量角色分离

jp_exit 默认 TOKYO_Standby，供 DMM、AbemaTV、Hulu Japan、Niconico 业务使用；capacity_exit 默认仍为同一节点，供下载、云同步等使用。两者为独立逻辑角色，调整容量节点不会通过角色映射连带改变日本业务。业务是否必须日本仍由独立约束说明；Niconico 仅为当前日本出口偏好，不新增必须日本的断言。

## 核心不等于三个域名

用户定义的核心 AI 范围是 OpenAI / Anthropic 之外的其他 AI 交互。OpenAI / Anthropic 单列，默认韩国；其余核心 AI 默认大阪。

现生成策略将这一范围分为 core_interactive 与 ai_other 两个业务文件，两者都映射 core_exit -> OSAKA_Premium。core_interactive 中 api.github.com、api.githubcopilot.com、perplexity.ai 是上一轮人工挑选的显式拆分种子，不是经过完整业务评估后证明只有这三个重要，也不是核心业务的完整定义。该命名拆分待后续统一，本次不合并或缩减列表。

ai_other 的来源是当前 AI_other.list，因此不代表已经覆盖所有已知 AI 产品。共享 Auth0/Stripe/Sentry 等被拆分，以及关键词等暂缓生成，意味着新候选不是旧列表的完整等价复制；不能声称所有原 AI 请求均已保持原路由。应在完整匹配与依赖审核后再上线。

本次仅新增日本角色、调整四个业务的角色引用及补充说明；不改核心来源、rule_overrides、共享依赖策略、生产 INI 或运行时选择。候选仍须审核，结果以新的 Actions 运行附件为准。
