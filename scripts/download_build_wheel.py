"""Download a pinned build wheel even when Docker's DNS is unavailable.

The hostname is resolved through DNS-over-HTTPS. The HTTPS connection then
uses the resolved IP directly while retaining the original hostname for SNI,
certificate verification, and the Host header.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import socket
import ssl
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit
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
            errors.append(f"{endpoint}: response did not contain IPv4 addresses")
        except Exception as exc:
            errors.append(f"{endpoint}: {exc}")
    raise RuntimeError("DNS-over-HTTPS failed: " + "; ".join(errors))


class ResolvedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that bypasses DNS without weakening TLS."""

    def __init__(self, hostname: str, address: str, timeout: int = 120):
        super().__init__(
            hostname,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self.resolved_address = address

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self.resolved_address, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


def download(url: str, output: Path, expected_sha256: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Only HTTPS wheel URLs are supported")
    request_path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    errors = []

    for address in resolve_ipv4(parsed.hostname):
        connection = ResolvedHTTPSConnection(parsed.hostname, address)
        temporary = output.with_suffix(output.suffix + ".part")
        try:
            connection.request(
                "GET",
                request_path,
                headers={
                    "Accept": "application/octet-stream",
                    "User-Agent": "chatbot-docker-build/1.0",
                },
            )
            response = connection.getresponse()
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status} {response.reason}")

            digest = hashlib.sha256()
            with temporary.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    handle.write(chunk)
            actual_sha256 = digest.hexdigest()
            if actual_sha256.lower() != expected_sha256.lower():
                raise RuntimeError(
                    f"SHA256 mismatch: expected {expected_sha256}, got {actual_sha256}"
                )
            temporary.replace(output)
            return
        except Exception as exc:
            errors.append(f"{address}: {exc}")
            temporary.unlink(missing_ok=True)
        finally:
            connection.close()

    raise RuntimeError("Wheel download failed: " + "; ".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha256", default="")
    args = parser.parse_args()

    fragment_hash = parse_qs(urlsplit(args.url).fragment).get("sha256", [""])[0]
    expected_sha256 = args.sha256 or fragment_hash
    if not expected_sha256:
        raise ValueError("A pinned SHA256 is required")

    download(args.url, args.output, expected_sha256)
    print(f"Downloaded and verified {args.output.name}")


if __name__ == "__main__":
    main()
