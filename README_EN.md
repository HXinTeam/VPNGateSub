# VPNGateSub

[中文](README.md) | **English**

Automatically fetch public [VPN Gate](https://www.vpngate.net) servers that support **OpenVPN**, parse embedded certificates, and generate **sing-box** and **mihomo (Clash.Meta)** configuration files. Automated and updated daily via GitHub Actions.

## Features

- **Country Grouping & Auto-Selection**: Nodes are automatically classified by country (with country flag emojis). Includes country-level URL-test groups (`🇯🇵 JP-AUTO`) and manual selection groups (`🇯🇵 JP`).
- **Global Smart Routing**: Comes with a global auto-speed test group (`AUTO`) and a primary selection group (`PROXY`).
- **Dual Client Support**:
  - **sing-box** (≥ 1.14): Full configuration with modern `openvpn-client` endpoints, mixed inbound, DNS hijacking, and selector/urltest outbound groups.
  - **mihomo (Clash.Meta)**: Standard configuration with inline CA/cert/key certificates, URL-test and select proxy groups.
- **Zero Third-Party Dependencies**: The generator script uses only the Python 3 standard library.
- **Daily Automated Updates**: Runs automatically via GitHub Actions every day at 00:00 UTC.

---

## Subscription Links

Subscribe directly in your client using the raw URLs from this repository:

```
https://raw.githubusercontent.com/<YourUsername>/<RepoName>/main/output/singbox.json
https://raw.githubusercontent.com/<YourUsername>/<RepoName>/main/output/mihomo.yaml
```

---

## Generated Files

| File | Description |
| --- | --- |
| `output/singbox.json` | Complete sing-box config (`openvpn-client` endpoints, requires sing-box ≥ 1.14; mixed inbound on `127.0.0.1:2080`, selector & urltest groups). |
| `output/mihomo.yaml` | Complete mihomo / Clash.Meta config (`type: openvpn` proxies with inline certificates, mixed port `7890`, selector & url-test groups). |

---

## Local Usage

Requires Python 3.9+ (Standard Library only):

```bash
# Fetch all nodes by default
python scripts/fetch_vpngate.py

# Limit to top 50 nodes
python scripts/fetch_vpngate.py --limit 50

# Filter by country codes (e.g. Japan and United States only)
python scripts/fetch_vpngate.py --countries JP,US

# Filter by minimum speed (Mbps) and maximum ping (ms)
python scripts/fetch_vpngate.py --min-speed 10 --max-ping 300

# Sort nodes by speed (options: score, speed, ping)
python scripts/fetch_vpngate.py --sort speed
```

### CLI Arguments

- `--limit`: Maximum number of nodes (`0` = all nodes, default: `0`).
- `--countries`: Comma-separated list of 2-letter country codes (e.g., `JP,US,KR`).
- `--min-speed`: Minimum link speed in Mbps (default: `0`).
- `--max-ping`: Maximum ping in milliseconds (default: `0` / unlimited).
- `--sort`: Sorting criterion: `score` (default), `speed`, or `ping`.
- `--output-dir`: Output directory for generated files (default: `output`).
- `--url`: API URL for VPN Gate CSV endpoint.
- `--retries` / `--timeout`: Network retry attempts and timeout in seconds.

---

## GitHub Actions Automation

- **Schedule**: Automatically runs every day at `00:00 UTC` (cron: `0 0 * * *`).
- **Manual Trigger**: Go to **Actions → Update VPN configs → Run workflow** to manually trigger an update with custom node limits or country filters.
- **Auto Commit**: Updates are validated and committed directly to the `main` branch.

---

## How It Works

1. Fetches the live server list from `https://www.vpngate.net/api/iphone/`.
2. Filters servers with valid `OpenVPN_ConfigData_Base64` fields, sorts them by score/speed, and eliminates duplicates.
3. Decodes the `.ovpn` profile to extract IP addresses, ports, transport protocol (`udp`/`tcp`), and embedded CA certificate, client certificate, and private key.
4. Generates structured JSON for sing-box (`openvpn-client` endpoints) and YAML for mihomo (`openvpn` proxies) with multi-level proxy groups.

---

## Disclaimer

This repository is for educational and research purposes only. VPN Gate is an academic experiment project operated by the University of Tsukuba, Japan. Please adhere to local laws and regulations when using this tool.
