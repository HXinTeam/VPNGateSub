# VPNGateSub

自动从 [VPN Gate](https://www.vpngate.net) 公共节点列表拉取支持 **OpenVPN** 的服务器，并生成 **sing-box** 与 **mihomo (Clash.Meta)** 配置文件，由 GitHub Actions 定时更新。

## 使用方法

1. Fork / 推送本仓库到 GitHub（Actions 默认开启）。
2. 工作流每 6 小时自动运行一次，也可在 **Actions → Update VPN configs → Run workflow** 手动触发（可指定节点数量与国家过滤）。
3. 运行成功后，`output/` 目录中的配置文件会自动提交，直接用 raw 链接订阅：

   ```
   https://raw.githubusercontent.com/<你的用户名>/<仓库名>/main/output/singbox.json
   https://raw.githubusercontent.com/<你的用户名>/<仓库名>/main/output/mihomo.yaml
   ```

## 生成文件

| 文件 | 说明 |
| --- | --- |
| `output/singbox.json` | sing-box 完整配置（OpenVPN 节点为 `openvpn-client` endpoint，需 sing-box ≥ 1.14；含 mixed 入站 127.0.0.1:2080、selector/urltest 分组） |
| `output/mihomo.yaml` | mihomo 配置（`type: openvpn` 代理，含 ca/cert/key 内联证书、select + url-test 分组、mixed 端口 7890） |

## 本地运行

仅需 Python 3.9+（纯标准库，无第三方依赖）：

```bash
python scripts/fetch_vpngate.py                       # 默认取评分前 30 个节点
python scripts/fetch_vpngate.py --limit 50            # 前 50 个节点
python scripts/fetch_vpngate.py --countries JP,US     # 只保留日本/美国
python scripts/fetch_vpngate.py --min-speed 10 --max-ping 300   # 速度/延迟过滤
python scripts/fetch_vpngate.py --sort speed          # 按速度排序（score/speed/ping）
```

常用参数：`--url`（API 地址）、`--output-dir`（输出目录）、`--retries`/`--timeout`。

## 工作原理

1. 拉取 `https://www.vpngate.net/api/iphone/` 的 CSV 列表；
2. 筛选 `OpenVPN_ConfigData_Base64` 非空（即支持 OpenVPN）的条目，按评分/速度排序并去重；
3. 解码内嵌的 `.ovpn` 配置，提取服务器地址、端口、协议（UDP/TCP）与 CA/客户端证书/私钥；
4. 分别渲染为 sing-box endpoint 与 mihomo proxy 格式写入 `output/`。

## 免责声明

本项目仅用于学习与研究。VPN Gate 是日本筑波大学的学术实验项目，请遵守当地法律法规，勿用于非法用途。
