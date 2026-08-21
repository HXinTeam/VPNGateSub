#!/usr/bin/env python3
"""Fetch VPN Gate servers that support OpenVPN and generate sing-box / mihomo configs.

Only Python standard library is required.
"""

import argparse
import base64
import binascii
import csv
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_API_URL = "https://www.vpngate.net/api/iphone/"
USER_AGENT = "Mozilla/5.0 (compatible; VPNGateSub/1.0; +https://github.com)"

MIHOMO_CIPHERS = {"AES-128-GCM", "AES-256-GCM", "AES-128-CBC", "AES-256-CBC", "CHACHA20-POLY1305"}
MIHOMO_AUTHS = {"MD5", "SHA1", "SHA256", "SHA384", "SHA512"}

PEM_RE = {
    "ca": re.compile(r"<ca>(.*?)</ca>", re.S),
    "cert": re.compile(r"<cert>(.*?)</cert>", re.S),
    "key": re.compile(r"<key>(.*?)</key>", re.S),
}
REMOTE_RE = re.compile(
    r"^[ \t]*remote[ \t]+([^ \t\r\n]+)[ \t]+(\d+)(?:[ \t]+([^ \t\r\n]+))?[ \t]*\r?$", re.M
)
DIRECTIVE_RE = lambda key: re.compile(
    rf"^[ \t]*{key}[ \t]+([A-Za-z0-9_.\-]+)[ \t]*\r?$", re.M | re.I
)
AUTH_USER_PASS_RE = re.compile(r"^[ \t]*auth-user-pass\b", re.M)
TLS_AUTH_RE = re.compile(r"<tls-auth>")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def fetch_api(url: str, retries: int, timeout: int) -> str:
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            text = data.decode("utf-8", errors="replace")
            if "HostName" in text and "," in text:
                return text
            raise ValueError("response does not look like a VPN Gate CSV list")
        except Exception as exc:
            last_exc = exc
            log(f"[warn] fetch failed ({attempt}/{retries}): {exc}")
            if attempt < retries:
                time.sleep(3 * attempt)
    raise SystemExit(f"[error] failed to download {url}: {last_exc}")


def parse_list(text: str) -> list:
    lines = text.splitlines()
    header = None
    start = 0
    for i, line in enumerate(lines):
        stripped = line.strip().lstrip("#").strip()
        if stripped and "HostName" in stripped and "," in stripped:
            header = [c.strip() for c in stripped.split(",")]
            start = i + 1
            break
    if not header:
        raise SystemExit("[error] cannot locate CSV header in VPN Gate response")

    rows = []
    reader = csv.reader(
        line for line in lines[start:] if line.strip() and not line.lstrip().startswith("#")
    )
    for fields in reader:
        if len(fields) < len(header):
            continue
        row = {header[i]: fields[i].strip() for i in range(len(header))}
        if row.get("OpenVPN_ConfigData_Base64"):
            rows.append(row)
    return rows


def to_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_proto(token: str) -> str:
    token = (token or "").strip().lower()
    for suffix in ("4", "6"):
        if token.endswith(suffix):
            token = token[: -len(suffix)]
    return token if token in ("udp", "tcp") else ""


def clean_pem(text: str) -> str:
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(ln for ln in lines if ln)


def parse_ovpn(b64_text: str) -> dict:
    conf = base64.b64decode(b64_text.strip()).decode("utf-8", errors="replace")

    node = {}
    remotes = REMOTE_RE.findall(conf)

    proto_match = DIRECTIVE_RE("proto").search(conf)
    proto_directive = normalize_proto(proto_match.group(1)) if proto_match else ""
    cipher_match = DIRECTIVE_RE("cipher").search(conf)
    auth_match = DIRECTIVE_RE("auth").search(conf)
    dc_match = DIRECTIVE_RE("data-ciphers").search(conf)
    comp_match = DIRECTIVE_RE("comp-lzo").search(conf)

    node["remote_host"] = remotes[0][0] if remotes else ""
    node["port"] = int(remotes[0][1]) if remotes else 1194
    remote_proto = normalize_proto(remotes[0][2]) if remotes and remotes[0][2] else ""
    node["proto"] = remote_proto or proto_directive or "udp"

    for name, regex in PEM_RE.items():
        match = regex.search(conf)
        node[name] = clean_pem(match.group(1)) if match else ""

    node["cipher"] = cipher_match.group(1).upper() if cipher_match else ""
    node["auth"] = auth_match.group(1).upper() if auth_match else ""
    node["data_ciphers"] = [c.upper() for c in dc_match.group(1).split(":") if c] if dc_match else []
    node["comp_lzo"] = comp_match.group(1).lower() if comp_match else ""
    node["auth_user_pass"] = bool(AUTH_USER_PASS_RE.search(conf))
    node["has_tls_auth"] = bool(TLS_AUTH_RE.search(conf))
    return node


def build_nodes(rows: list, args) -> list:
    countries = {c.strip().upper() for c in args.countries.split(",") if c.strip()}
    nodes, seen, skipped = [], set(), 0

    candidates = []
    for row in rows:
        cc = (row.get("CountryShort") or "").upper()
        if countries and cc not in countries:
            continue
        speed = to_int(row.get("Speed"))
        ping = to_int(row.get("Ping"), 99999)
        if args.min_speed and speed < args.min_speed * 1_000_000:
            continue
        if args.max_ping and ping > args.max_ping:
            continue
        score = to_int(row.get("Score"))
        candidates.append((-score if args.sort == "score" else -speed if args.sort == "speed" else ping,
                           -speed, row))

    candidates.sort(key=lambda item: (item[0], item[1]))
    for _, _, row in candidates:
        if args.limit and len(nodes) >= args.limit:
            break
        try:
            info = parse_ovpn(row["OpenVPN_ConfigData_Base64"])
        except Exception as exc:
            skipped += 1
            log(f"[warn] skip unreadable config ({row.get('HostName')}): {exc}")
            continue
        if info["has_tls_auth"]:
            skipped += 1
            log("[warn] skip node with unsupported tls-auth")
            continue
        if not info["ca"]:
            skipped += 1
            log("[warn] skip node without embedded CA certificate")
            continue

        server = row.get("IP") or info["remote_host"]
        if not server:
            skipped += 1
            continue
        dedupe_key = (server, info["port"], info["proto"])
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        use_cert = bool(info["cert"] and info["key"])
        cc = (row.get("CountryShort") or "VPN").upper()
        nodes.append({
            "name": cc,
            "country_code": cc,
            "country_long": row.get("CountryLong") or "",
            "server": server,
            "port": info["port"],
            "proto": info["proto"],
            "ca": info["ca"],
            "cert": info["cert"] if use_cert else "",
            "key": info["key"] if use_cert else "",
            "username": "" if use_cert else "vpn",
            "password": "" if use_cert else "vpn",
            "cipher": info["cipher"] if info["cipher"] in MIHOMO_CIPHERS else "",
            "auth": info["auth"] if info["auth"] in MIHOMO_AUTHS else "",
            "data_ciphers": [c for c in info["data_ciphers"] if c != "NONE"],
            "comp_lzo": info["comp_lzo"] if info["comp_lzo"] in ("yes", "no", "adaptive") else "",
            "speed_mbps": round(to_int(row.get("Speed")) / 1_000_000, 1),
            "ping_ms": to_int(row.get("Ping")),
            "sessions": to_int(row.get("NumVpnSessions")),
        })

    counters = {}
    for node in nodes:
        cc = node["country_code"]
        idx = counters.get(cc, 0) + 1
        counters[cc] = idx
        node["name"] = f"{cc}-{idx:02d}"

    log(f"[info] usable OpenVPN nodes: {len(nodes)} (skipped {skipped})")
    return nodes


def yq(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def yaml_pem(key: str, pem: str, indent: str = "    ") -> list:
    lines = [f"{indent}{key}: |"]
    lines += [f"{indent}  {line}" for line in pem.strip().splitlines()]
    return lines


def build_singbox(nodes: list) -> dict:
    endpoints, tags = [], []
    country_nodes = {}
    for node in nodes:
        tls = {"certificate": node["ca"]}
        if node["cert"] and node["key"]:
            tls["client_certificate"] = node["cert"]
            tls["client_key"] = node["key"]
        endpoint = {
            "type": "openvpn-client",
            "tag": node["name"],
            "server": node["server"],
            "server_port": node["port"],
            "network": node["proto"],
            "mtu": 1500,
            "tls": tls,
        }
        if node["username"]:
            endpoint["username"] = node["username"]
            endpoint["password"] = node["password"]
        if node["data_ciphers"]:
            endpoint["data_ciphers"] = node["data_ciphers"]
            if node["cipher"]:
                endpoint["data_ciphers_fallback"] = node["cipher"]
        elif node["cipher"]:
            endpoint["data_ciphers"] = [node["cipher"]]
            endpoint["data_ciphers_fallback"] = node["cipher"]
        if node["auth"]:
            endpoint["auth"] = node["auth"]
        if node["comp_lzo"] in ("yes", "adaptive"):
            endpoint["compression_lzo"] = node["comp_lzo"]
        endpoints.append(endpoint)
        tags.append(node["name"])
        country_nodes.setdefault(node["country_code"], []).append(node["name"])

    country_autos = [f"{cc}-AUTO" for cc in country_nodes]
    country_selects = [cc for cc in country_nodes]

    outbounds = [
        {
            "type": "selector",
            "tag": "PROXY",
            "outbounds": ["AUTO", *country_autos, *country_selects, "direct", *tags],
            "default": "AUTO",
            "interrupt_exist_connections": True,
        },
        {
            "type": "urltest",
            "tag": "AUTO",
            "outbounds": tags,
            "url": "https://www.gstatic.com/generate_204",
            "interval": "10m",
            "tolerance": 50,
        },
    ]

    for cc, c_tags in country_nodes.items():
        outbounds.append({
            "type": "urltest",
            "tag": f"{cc}-AUTO",
            "outbounds": c_tags,
            "url": "https://www.gstatic.com/generate_204",
            "interval": "10m",
            "tolerance": 50,
        })
        outbounds.append({
            "type": "selector",
            "tag": cc,
            "outbounds": [f"{cc}-AUTO", *c_tags],
            "default": f"{cc}-AUTO",
            "interrupt_exist_connections": True,
        })

    outbounds.append({"type": "direct", "tag": "direct"})
    if not endpoints:
        outbounds = [{"type": "direct", "tag": "direct"}]

    return {
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "servers": [
                {"type": "local", "tag": "local"},
                {"type": "udp", "tag": "remote-dns", "server": "8.8.8.8"},
            ],
            "final": "local",
        },
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": 2080,
            }
        ],
        "endpoints": endpoints,
        "outbounds": outbounds,
        "route": {
            "rules": [
                {"action": "sniff"},
                {"protocol": "dns", "action": "hijack-dns"},
            ],
            "final": "PROXY" if endpoints else "direct",
            "auto_detect_interface": True,
            "default_domain_resolver": {"server": "local"},
        },
    }


def build_mihomo(nodes: list) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# mihomo (Clash.Meta) config generated by VPNGateSub at {now}",
        "# Source: https://www.vpngate.net/api/iphone/",
        "mixed-port: 7890",
        "allow-lan: false",
        "mode: rule",
        "log-level: info",
        "ipv6: false",
        "unified-delay: true",
        "tcp-concurrent: true",
        "external-controller: 127.0.0.1:9090",
        "profile:",
        "  store-selected: true",
        "",
        "proxies:",
    ]

    country_nodes = {}
    for node in nodes:
        lines.append(f"  - name: {yq(node['name'])}")
        lines.append("    type: openvpn")
        lines.append(f"    server: {node['server']}")
        lines.append(f"    port: {node['port']}")
        lines.append(f"    proto: {node['proto']}")
        lines.append(f"    udp: {'true' if node['proto'] == 'udp' else 'false'}")
        if node["cert"] and node["key"]:
            lines += yaml_pem("ca", node["ca"], indent="    ")
            lines += yaml_pem("cert", node["cert"], indent="    ")
            lines += yaml_pem("key", node["key"], indent="    ")
        else:
            lines.append("    username: vpn")
            lines.append("    password: vpn")
            lines += yaml_pem("ca", node["ca"], indent="    ")
        if node["cipher"]:
            lines.append(f"    cipher: {node['cipher']}")
        if node["auth"]:
            lines.append(f"    auth: {node['auth']}")
        if node["comp_lzo"]:
            lines.append(f"    comp-lzo: \"{node['comp_lzo']}\"")
        lines.append("")
        lines.append(f"# {node['country_long']} | {node['sessions']} users online")
        country_nodes.setdefault(node["country_code"], []).append(node["name"])

    names = [n["name"] for n in nodes]
    country_autos = [f"{cc}-AUTO" for cc in country_nodes]
    country_selects = [cc for cc in country_nodes]

    lines += [
        "",
        "proxy-groups:",
        "  - name: PROXY",
        "    type: select",
        "    proxies:",
        "      - AUTO",
    ]
    lines += [f"      - {yq(ca)}" for ca in country_autos]
    lines += [f"      - {yq(cs)}" for cs in country_selects]
    lines += ["      - DIRECT"]
    lines += [f"      - {yq(name)}" for name in names]

    lines += [
        "  - name: AUTO",
        "    type: url-test",
        "    url: https://www.gstatic.com/generate_204",
        "    interval: 300",
        "    tolerance: 50",
        "    proxies:",
    ]
    lines += [f"      - {yq(name)}" for name in names]

    for cc, c_names in country_nodes.items():
        lines += [
            f"  - name: {yq(f'{cc}-AUTO')}",
            "    type: url-test",
            "    url: https://www.gstatic.com/generate_204",
            "    interval: 300",
            "    tolerance: 50",
            "    proxies:",
        ]
        lines += [f"      - {yq(name)}" for name in c_names]
        lines += [
            f"  - name: {yq(cc)}",
            "    type: select",
            "    proxies:",
            f"      - {yq(f'{cc}-AUTO')}",
        ]
        lines += [f"      - {yq(name)}" for name in c_names]

    lines += ["", "rules:", f"  - MATCH,{'PROXY' if names else 'DIRECT'}", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sing-box/mihomo configs from VPN Gate")
    parser.add_argument("--url", default=DEFAULT_API_URL, help="VPN Gate CSV API URL")
    parser.add_argument("--output-dir", default="output", help="directory for generated configs")
    parser.add_argument("--limit", type=int, default=0, help="max number of nodes (0 = all)")
    parser.add_argument("--min-speed", type=float, default=0, help="minimum link speed in Mbps")
    parser.add_argument("--max-ping", type=int, default=0, help="maximum ping in ms (0 = unlimited)")
    parser.add_argument("--countries", default="", help="comma separated country codes filter, e.g. JP,US")
    parser.add_argument("--sort", choices=("score", "speed", "ping"), default="score")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    args.limit = max(0, args.limit)
    text = fetch_api(args.url, args.retries, args.timeout)
    rows = parse_list(text)
    log(f"[info] fetched {len(rows)} servers with OpenVPN support from API")

    nodes = build_nodes(rows, args)
    if not nodes:
        raise SystemExit("[error] no usable OpenVPN nodes after filtering")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    singbox_path = out_dir / "singbox.json"
    singbox_path.write_text(
        f"// Generated by VPNGateSub at "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        + json.dumps(build_singbox(nodes), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    mihomo_path = out_dir / "mihomo.yaml"
    mihomo_path.write_text(build_mihomo(nodes), encoding="utf-8")

    log(f"[done] wrote {singbox_path} and {mihomo_path} with {len(nodes)} nodes")


if __name__ == "__main__":
    main()
