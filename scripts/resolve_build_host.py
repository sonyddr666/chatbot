"""Resolve a build dependency through DNS-over-HTTPS.

This is only used inside the Docker builder when the daemon DNS cannot resolve
download.pytorch.org. The resulting entry is scoped to the disposable build
container and never changes the host or the application data volume.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


DOH_ENDPOINTS = (
    "https://1.1.1.1/dns-query?name={hostname}&type=A",
    "https://8.8.8.8/resolve?name={hostname}&type=A",
)


def resolve_ipv4(hostname: str) -> list[str]:
    errors = []
    for template in DOH_ENDPOINTS:
        endpoint = template.format(hostname=quote(hostname, safe=""))
        request = Request(endpoint, headers={"Accept": "application/dns-json"})
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.load(response)
            addresses = sorted({
                str(answer.get("data", "")).strip()
                for answer in payload.get("Answer", [])
                if answer.get("type") == 1 and answer.get("data")
            })
            if addresses:
                return addresses
            errors.append(f"{endpoint}: resposta sem IPv4")
        except Exception as exc:
            errors.append(f"{endpoint}: {exc}")
    raise RuntimeError("Falha no DNS-over-HTTPS: " + "; ".join(errors))


def append_hosts(hostname: str, addresses: list[str], hosts_file: Path) -> None:
    with hosts_file.open("a", encoding="utf-8") as handle:
        for address in addresses:
            handle.write(f"\n{address}\t{hostname}")
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("hostname")
    parser.add_argument("--hosts-file", type=Path, default=Path("/etc/hosts"))
    args = parser.parse_args()
    addresses = resolve_ipv4(args.hostname)
    append_hosts(args.hostname, addresses, args.hosts_file)
    print(f"Resolved {args.hostname} with {len(addresses)} IPv4 address(es)")


if __name__ == "__main__":
    main()
