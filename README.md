# clashrule

OpenClash 分流规则仓库。配合第三方转换服务生成本机运行配置（`vless.yaml`）。

## 文件结构

- **`virgil-v2.ini`** —— 生产模板：规则集引用 + 代理组定义（OpenClash 的 `custom_template_url` 指向它）
- **`*.list`** —— 被模板引用的分流规则集（按用途命名，如 `AppleStore.list` / `MediaHK.list` / `AI_other.list`）
- **`archive/`** —— 已停用、无引用的历史文件（用途、停用原因、恢复方式见 `archive/README.md`）

## 运维约定

### 1. 改模板必须同步更新 `?v=` 戳（缓存击穿）

转换服务**按完整 URL 缓存**转换结果：模板 URL 不变 → 直接返回旧缓存 → **规则改了却不生效**（排查时极具迷惑性：仓库是新的、运行配置是旧的）。

因此 `custom_template_url` 采用带版本戳的形式：

```
https://raw.githubusercontent.com/virgilshwork/clashrule/main/virgil-v2.ini?v=<YYYYMMDD_HHMM>
```

**每次改动 `virgil-v2.ini` 或任一 `*.list` 之后，必须把 `?v=` 换成当前时间戳**，再去 OpenClash 点"更新配置"，新规则才会生效。

```bash
# 查看当前戳值
uci get openclash.@config_subscribe[0].custom_template_url
# 更新戳值（改完记得 commit）
uci set openclash.@config_subscribe[0].custom_template_url='https://raw.githubusercontent.com/virgilshwork/clashrule/main/virgil-v2.ini?v=<新戳>'
uci commit openclash
```

> 不要为了"干净"去掉 `?v=`：去掉就失去唯一可靠的缓存击穿手段，规则改动会静默不生效。

### 2. 节点参数有两个源头（高频踩坑）

**订阅内容**（`config_subscribe[0].address`，即 vless 节点列表）里的参数**会覆盖**本机修复。典型表现：手动"更新配置"后，部分节点的 端口 / SNI / uuid / 公钥 被回滚成老值。

- **服务端参数变更后，必须同步修订阅内容**（否则每次更新都会被回滚）
- 本机保留每小时自愈任务（`oc_selfheal.py`）作安全网：比对 `地址 / 端口 / SNI / uuid`，检出漂移即修并重启

### 3. 生效验证（改完必做）

```bash
# 规则与组数量
grep -c '^\s*- ' /etc/openclash/vless.yaml
# 指定规则是否进了运行配置
grep -c '17.8.0.0/16' /etc/openclash/vless.yaml
grep -c '苹果商店' /etc/openclash/vless.yaml
```

