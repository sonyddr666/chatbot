"""Cloudflare account discovery for Workers AI custom providers."""

from __future__ import annotations

import httpx


CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"


def workers_ai_base_url(account_id: str) -> str:
    normalized = str(account_id or "").strip()
    if not normalized or any(char not in "0123456789abcdefABCDEF" for char in normalized):
        raise ValueError("Account ID da Cloudflare invalido")
    return f"{CLOUDFLARE_API_BASE}/accounts/{normalized}/ai/v1"


async def discover_cloudflare_accounts(api_token: str) -> list[dict]:
    token = str(api_token or "").strip()
    if not token:
        raise ValueError("Informe um API Token da Cloudflare")

    timeout = httpx.Timeout(20.0, connect=8.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(
            f"{CLOUDFLARE_API_BASE}/accounts",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params={"per_page": 50},
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Cloudflare respondeu HTTP {response.status_code} sem JSON valido") from exc

    if response.status_code >= 400 or not payload.get("success", False):
        errors = payload.get("errors") or []
        detail = "; ".join(
            str(item.get("message") or item) if isinstance(item, dict) else str(item)
            for item in errors
        ) or f"HTTP {response.status_code}"
        raise RuntimeError(
            "Nao foi possivel listar as contas Cloudflare. Verifique se o token tem acesso a Account Settings: Read. "
            + detail
        )

    accounts = []
    for item in payload.get("result") or []:
        if not isinstance(item, dict):
            continue
        account_id = str(item.get("id") or "").strip()
        if not account_id:
            continue
        accounts.append({
            "id": account_id,
            "name": str(item.get("name") or account_id),
        })
    return accounts
