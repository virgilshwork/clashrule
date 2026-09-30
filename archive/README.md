# archive — 已停用的历史文件

归档日期：2026-09-30

以下文件**不再被任何配置引用**，仅作历史留档（git 历史亦可追溯）。除本 README 外，
本目录内容不应被任何订阅转换或路由器配置引用。

| 文件 | 原用途 | 停用原因 |
|---|---|---|
| `virgil.ini` | ClashRule v1 模板（33 组） | 生产已改用 `virgil-v2.ini`（45 组）。路由器 `custom_template_url` 只指向 v2。 |
| `policy.ini` | 更早一代模板（43 组，含 `01_special`/`01_denykids`/`01_softether`/`01_video` 等已不存在文件的引用） | 非生产模板；引用的列表文件多数已不存在，引用链已断。 |
| `custom_ruleset.txt` | 早期片段式 ruleset 清单 | 引用的 `01_cryptoAll.list`、`01_softether.list` 均已不存在；非生产引用。 |

## 恢复方式

如需重新启用某个文件，把它移回仓库根目录，并在订阅转换的 `custom_template_url`
中显式指向新路径即可（当前生产指向 `virgil-v2.ini`）。
