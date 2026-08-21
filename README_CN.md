# VPNGateSub

[English](README.md) | **中文**

自动从 [VPN Gate](https://www.vpngate.net) 公共节点列表拉取支持 **OpenVPN** 的服务器，并生成 **sing-box** 与 **mihomo (Clash.Meta)** 配置文件，由 GitHub Actions 定时更新。

## 特性

- **国家自动分类与优选**：节点按国家自动分类并带有国旗 Emoji，每个国家生成独立的延迟测速组（`🇯🇵 JP-AUTO`）和手动选择组（`🇯🇵 JP`）。
- **全局智能路由**：提供全局自动优选组（`AUTO`）和主选择组（`PROXY`）。
- **双客户端适配**：
  - **sing-box**（≥ 1.14）：完整配置，采用现代 `openvpn-client` endpoint 格式，支持 mixed 入站、DNS 劫持及 selector/urltest 分组。
  - **mihomo (Clash.Meta)**：标准配置，证书内联（CA/cert/key），支持 select 与 url-test 策略组。
- **纯标准库实现**：无任何第三方 Python 依赖。
- **每日定时更新**：通过 GitHub Actions 每天 UTC 00:00 自动更新。

---

## 订阅链接

在客户端中直接使用本仓库的 raw 链接进行订阅：

```
https://raw.githubusercontent.com/<你的用户名>/<仓库名>/main/output/singbox.json
https://raw.githubusercontent.com/<你的用户名>/<仓库名>/main/output/mihomo.yaml
```

---

## 生成文件

| 文件 | 说明 |
| --- | --- |
| `output/singbox.json` | sing-box 完整配置（OpenVPN 节点为 `openvpn-client` endpoint，需 sing-box ≥ 1.14；含 mixed 入站 127.0.0.1:2080、selector/urltest 分组） |
| `output/mihomo.yaml` | mihomo 配置（`type: openvpn` 代理，含 ca/cert/key 内联证书、select + url-test 分组、mixed 端口 7890） |

---

## 本地运行

仅需 Python 3.9+（纯标准库，无第三方依赖）：

```bash
# 默认拉取全部节点
python scripts/fetch_vpngate.py

# 限制前 50 个节点
python scripts/fetch_vpngate.py --limit 50

# 按国家代码过滤（例如仅保留日本和美国）
python scripts/fetch_vpngate.py --countries JP,US

# 过滤最小速度 (Mbps) 与最大延迟 (ms)
python scripts/fetch_vpngate.py --min-speed 10 --max-ping 300

# 按速度排序（可选：score, speed, ping）
python scripts/fetch_vpngate.py --sort speed
```

### CLI 参数说明

- `--limit`：最大节点数（`0` 表示全部，默认：`0`）。
- `--countries`：国家代码逗号分隔列表（例如：`JP,US,KR`）。
- `--min-speed`：最低连接速度 Mbps（默认：`0`）。
- `--max-ping`：最大延迟毫秒（默认：`0` / 不限制）。
- `--sort`：排序依据：`score`（默认评分）、`speed`（速度）、`ping`（延迟）。
- `--output-dir`：生成文件输出目录（默认：`output`）。
- `--url`：VPN Gate CSV API 地址。
- `--retries` / `--timeout`：重试次数与超时秒数。

---

## GitHub Actions 自动更新

- **定时触发**：每日 UTC 00:00 自动运行（北京时间 08:00）。
- **手动触发**：前往 **Actions → Update VPN configs → Run workflow** 可手动触发更新并传入自定义参数。
- **自动提交**：生成并通过校验后自动推送到 `main` 分支。

---

## 工作原理

1. 从 `https://www.vpngate.net/api/iphone/` 拉取最新服务器列表；
2. 筛选 `OpenVPN_ConfigData_Base64` 非空的条目，按评分/速度排序并去重；
3. 解码内嵌的 `.ovpn` 配置，提取 IP 地址、端口、传输协议（UDP/TCP）以及内嵌的 CA、客户端证书与私钥；
4. 渲染为 sing-box endpoint 与 mihomo proxy 格式写入 `output/`。

---

## 免责声明

本项目仅用于学习与研究。VPN Gate 是日本筑波大学的学术实验项目，请遵守当地法律法规，勿用于非法用途。
