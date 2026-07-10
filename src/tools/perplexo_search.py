"""Safe HTTP adapter for the external Perplexo research service."""

from __future__ import annotations

from typing import Any

import httpx

from src.config import settings


class PerplexoError(RuntimeError):
    """Raised when the Perplexo service cannot produce a usable response."""


def _answer_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [_answer_text(item) for item in value]
        return "\n".join(part for part in parts if part)
    if not isinstance(value, dict):
        return ""

    for key in ("answer", "response", "result", "content", "text", "message", "output"):
        if key in value:
            text = _answer_text(value[key])
            if text:
                return text
    if "data" in value:
        return _answer_text(value["data"])
    return ""


def _citation_lines(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("citations") or payload.get("sources") or []
    if isinstance(raw, dict):
        raw = list(raw.values())
    if not isinstance(raw, list):
        return []

    lines: list[str] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, str):
            label, url = f"Fonte {index}", item.strip()
        elif isinstance(item, dict):
            label = str(item.get("title") or item.get("name") or f"Fonte {index}").strip()
            url = str(item.get("url") or item.get("link") or item.get("source") or "").strip()
        else:
            continue
        if url:
            lines.append(f"- [{label}]({url})")
    return lines


def _format_response(payload: Any) -> str:
    answer = _answer_text(payload)
    if not answer:
        raise PerplexoError("Perplexo respondeu sem conteudo utilizavel")
    citations = _citation_lines(payload)
    if citations and not any(line.split("](", 1)[-1].rstrip(")") in answer for line in citations):
        return answer + "\n\nFontes:\n" + "\n".join(citations)
    return answer


def _headers() -> dict[str, str]:
    api_key = settings.mcp_api_key.strip()
    if not api_key:
        raise PerplexoError("MCP_API_KEY nao configurada no servidor")
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }


def _timeout(seconds: float | None = None) -> httpx.Timeout:
    total = max(float(seconds or settings.perplexo_timeout_seconds), 2.0)
    return httpx.Timeout(total, connect=min(total, 5.0))


async def perplexo_search(
    query: str,
    user_id: int,
    *,
    model: str = "best",
    focus: str = "web",
    time_range: str = "week",
    citation_mode: str = "markdown",
    client: httpx.AsyncClient | None = None,
) -> str:
    """Search Perplexo while keeping credentials and user history isolated."""
    clean_query = query.strip()
    if not clean_query:
        raise PerplexoError("A consulta de pesquisa esta vazia")

    payload = {
        "query": clean_query,
        "user_id": str(user_id),
        "model": model,
        "focus": focus,
        "time_range": time_range,
        "citation_mode": citation_mode,
    }
    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        base_url=settings.perplexo_base_url.rstrip("/"),
        timeout=_timeout(),
        follow_redirects=True,
    )
    try:
        response = await active_client.post("/search", headers=_headers(), json=payload)
        if response.status_code >= 400:
            detail = response.text.strip()[:300]
            raise PerplexoError(f"Perplexo retornou HTTP {response.status_code}: {detail}")
        try:
            data = response.json()
        except ValueError as exc:
            raise PerplexoError("Perplexo retornou uma resposta que nao e JSON") from exc
        return _format_response(data)
    except httpx.TimeoutException as exc:
        raise PerplexoError("Perplexo excedeu o tempo limite") from exc
    except httpx.RequestError as exc:
        raise PerplexoError(f"Perplexo indisponivel: {exc.__class__.__name__}") from exc
    finally:
        if owns_client:
            await active_client.aclose()


async def perplexo_health(client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """Check connectivity without exposing the configured API key."""
    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        base_url=settings.perplexo_base_url.rstrip("/"),
        timeout=_timeout(6.0),
        follow_redirects=True,
    )
    try:
        response = await active_client.get("/health", headers=_headers())
        if response.status_code >= 400:
            raise PerplexoError(f"Perplexo health retornou HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            payload = {"message": response.text.strip()[:300]}
        return {
            "online": True,
            "status_code": response.status_code,
            "service": payload,
        }
    except httpx.TimeoutException as exc:
        raise PerplexoError("Perplexo nao respondeu ao teste em 6 segundos") from exc
    except httpx.RequestError as exc:
        raise PerplexoError(f"Nao foi possivel conectar ao Perplexo: {exc.__class__.__name__}") from exc
    finally:
        if owns_client:
            await active_client.aclose()
