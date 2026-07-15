"""Current-weather lookup through the public wttr.in text endpoint."""

from __future__ import annotations

from urllib.parse import quote

import httpx


async def get_weather(city: str) -> str:
    normalized = (city or "").strip()
    if not normalized:
        raise ValueError("Cidade nao pode ser vazia")
    if len(normalized) > 120 or any(ord(char) < 32 for char in normalized):
        raise ValueError("Cidade invalida")
    url = f"https://wttr.in/{quote(normalized, safe='')}"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.get(url, params={"format": "%C %t %w %h"})
        if response.status_code != 200:
            raise RuntimeError(f"Servico de clima respondeu HTTP {response.status_code}")
        text = response.text.strip()[:500]
        if not text:
            raise RuntimeError("Servico de clima retornou resposta vazia")
        return f"Clima em **{normalized}**: {text}"
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Falha ao consultar o clima: {exc}") from exc


TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Obtem o clima atual de uma cidade",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Nome da cidade, por exemplo Sao Paulo"}
            },
            "required": ["city"],
        },
    },
}
