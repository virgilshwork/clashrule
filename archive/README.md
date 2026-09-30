# archive — 已停用的历史文件

归档日期：2026-09-30

以下文件**不再被任何配置引用**，仅作历史留档（git 历史亦可追溯）。除本 README 外，
本目录内容不应被任何订阅转换或路由器配置引用。

| 文件 | 原用途 | 停用原因 |
|---|---|---|
| `virgil.ini` | ClashRule v1 模板（33 组） | 生产已改用 `virgil-v2.ini`（45 组）。路由器 `custom_template_url` 只指向 v2。 |
| `policy.ini` | 更早一代模板（43 组，含 `01_special`/`01_denykids`/`01_softether`/`01_video` 等已不存在文件的引用） | 非生产模板；引用的列表文件多数已不存在，引用链已断。 |
| `custom_ruleset.txt` | 早期片段式 ruleset 清单 | 引用的 `01_cryptoAll.list`、`01_softether.list` 均已不存在；非生产引用。 |

## 第二批（2026-09-30）：未被 `virgil-v2.ini` 引用的列表/片段文件

判定方法：对唯一生产模板 `virgil-v2.ini` 全文扫描 `ruleset=` / `rules=` 的引用目标，
逐文件 `grep -c` 命中数均为 **0**，故移入本目录。仓库根目录现只保留被引用的
17 个列表文件 + `virgil-v2.ini` + `README.md`。

| 文件 | 内容 | 停用原因 |
|---|---|---|
| `01_denykids.list` | 74 条（bilivideo/bilibili 等关键词拦截） | 未被引用；与 `kids.list` 高度重复 |
| `kids.list` | 63 条（同类关键词拦截） | 未被引用；与 `01_denykids.list` 内容近乎一致 |
| `banad.list` | 63 条（同类关键词拦截） | 未被引用；ini 引用的是远端 ACL4SSR 的 `BanAD.list`（大小写不同的另一个文件） |
| `AI.list` | 113 条 AI 服务域名 | 已被 `AI_other.list`（82 条）取代；归档 `policy.ini`/`custom_ruleset.txt` 后失去最后引用 |
| `02_openai_anthropic.list` | 8 条（OpenAI/Anthropic） | 内容已并入 `AI_other.list` |
| `01_dns.list` | 14 条（amazon/google 关键词） | 未被引用 |
| `01_video.list` | 2 条（rumble/thetvdb） | 未被引用 |
| `custom_proxy_group.txt` | 6 条策略组片段 | v2 的策略组已内联在 `virgil-v2.ini` |
| `policy` | 92 条（`- DOMAIN-SUFFIX,...,DIRECT` 形式的片段） | 早期规则集遗留，未被引用 |
| `softether` | 11 条 softether 直连片段 | 已被 `01_direct.list` 覆盖，未被引用 |

## 恢复方式

如需重新启用某个文件，把它移回仓库根目录，并在订阅转换的 `custom_template_url`
中显式指向新路径即可（当前生产指向 `virgil-v2.ini`）。
