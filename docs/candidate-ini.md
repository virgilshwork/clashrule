# 引用式候选 SubConverter INI

沿用 virgil-v2.ini 的组织方式：INI 引用规则文件，而不是暴露全部域名/IP 正文。业务规则与角色/业务组分离，不覆盖现有生产 INI。

## 发布布局

main 下 candidates/virgil-candidate.ini 是最新候选入口，candidates/manifest.json 记录发布版本。完整候选位于 candidates/snapshots/<publication-id>/，其中 rules/<business>.list 保留各业务完整列表；rules/ordered/ 保存供 INI 按顺序引用的片段。同一快照目录还包含 INI、业务映射与验证清单。

INI 中仅 GEOIP,CN 和 FINAL 两条兜底保持内联；业务正文全部引用 raw.githubusercontent.com/virgilshwork/clashrule/main/candidates/snapshots/<id>/rules/ordered/ 下的文件。该地址只有工作流发布提交成功后才真实可用。生成器、规则片段和 INI 不会因为仅提交安装代码就自动变成已发布结果。

## 为什么有 ordered 片段

不同业务的父域与子域规则可能互相覆盖。不能将每个完整业务文件机械加载一次并声称保持原全局排序。发布器把现有排序中同一业务的连续规则合为片段，使用不同的编号文件保留全部顺序；片段是执行层分块，不是新增业务分类。完整的 31 个业务列表仍保留供维护和审核，部分可为空。按片段重建必须与生成器原顺序完全一致，否则停止。

片段数可能多于业务文件数；这提高远程请求数量，应实测转换耗时。后续可以审核后减少片段，但不能在未知覆盖关系下随意合并。保留原排序不代表原排序已完全正确。

## 不可变版本与发布

publication-id 根据生成配置、规则文件及业务映射计算。原版本目录不覆盖、不自动清理；相同输入不新增版本。每次在同一 Git 提交内发布新快照、最新入口与清单，避免新 INI 引用尚未提交的规则。INI 指向版本路径，而非可变 rules/latest，旧缓存入口也能继续引用旧快照。

工作流仍支持推送相关脚本/策略触发、成功来源同步后触发以及手动运行。它现在具备 contents: write，但只暂存提交 candidates/。不改来源快照、根目录业务列表、virgil-v2.ini 或路由器；候选发布不是生产部署。不得把人工文件放入托管发布目录。现有未托管目录会拒绝覆盖。

分支保护或 main 并发更新可能导致推送失败；不强推，查看错误后重新运行。候选自身提交不在路径触发条件中，不产生循环。初次发布成功前不能使用候选入口 URL。历史附件不会删除。

## 策略与验收

GitHub 网页/API 与其他 AI 默认大阪；OpenAI/Anthropic、普通海外与视频默认韩国；下载默认东京；香港专项默认 Evoxt 香港；日本专项使用独立 jp_exit（东京）。GGC 仅手动备用，GGC A 的可达性须另行验收。原生成器内部先生成内嵌中间结果用于校验，发布器会覆盖为引用式最终产物，最终附件不保留内嵌版本。

此前七项域名断言、组引用和声明地区约束检查保留，新增片段顺序重建和不允许业务内联检查。INI SHA-256 更新为引用式内容。ini-validation.json 中 remote_files_published 故意标为需工作流推送确认，真正发布状态以 Summary 和提交为准。

ready_for_production 仍为 false；未执行 SubConverter、mihomo、DNS/IP 路由、认证或实际服务验收。审查 conflicts/pending/parse-issues，再在测试配置完成转换和功能验证。沿用 overwrite_original_rules=true，务必确认不需要保留订阅原始私有规则。

本地：先生成 business-output，再运行 python scripts/publish_candidate_references.py --input business-output --publish-root candidates。需要现有生成模块、Python 3.12、PyYAML 6.0.2。脚本只写本地目录，不自行提交或推送。
