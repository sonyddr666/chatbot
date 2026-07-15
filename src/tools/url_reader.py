"""Bounded HTTP(S) reader with SSRF protection and plain-text extraction."""

from __future__ import annotations

from html.parser import HTMLParser
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 24_000
MAX_REDIRECTS = 4


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.ignored += 1
        elif not self.ignored and tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.ignored:
            self.ignored -= 1
        elif not self.ignored and tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.ignored:
            text = " ".join(data.split())
            if text:
                self.parts.append(text + " ")

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line)[:MAX_TEXT_CHARS]


def _validate_public_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("A URL deve usar http ou https")
    if parsed.username or parsed.password:
        raise ValueError("Credenciais embutidas na URL nao sao permitidas")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError("Host da URL nao foi encontrado") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("URLs locais, privadas ou reservadas nao sao permitidas")
    return parsed.geturl()


async def read_url_content(url: str) -> dict:
    current = _validate_public_url(url)
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=8), follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            async with client.stream("GET", current, headers={"User-Agent": "ChatbotAgent/1.0"}) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise RuntimeError("Redirecionamento sem destino")
                    current = _validate_public_url(urljoin(current, location))
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if content_type and not (
                    content_type.startswith("text/")
                    or content_type in {"application/json", "application/xml", "application/xhtml+xml"}
                ):
                    raise ValueError(f"Tipo de conteudo nao suportado: {content_type}")
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > MAX_RESPONSE_BYTES:
                        raise ValueError("Conteudo da URL excede 2 MB")
                encoding = response.encoding or "utf-8"
                raw = bytes(chunks).decode(encoding, errors="replace")
                if "html" in content_type or "<html" in raw[:500].lower():
                    parser = _TextExtractor()
                    parser.feed(raw)
                    text = parser.text()
                else:
                    text = raw[:MAX_TEXT_CHARS]
                return {
                    "url": current,
                    "content_type": content_type or "text/plain",
                    "text": text,
                    "truncated": len(raw) > MAX_TEXT_CHARS,
                }
    raise RuntimeError("A URL excedeu o limite de redirecionamentos")
