"""Ferramenta de clima/weather (exemplo de function calling)."""

from typing import Optional
import httpx


async def get_weather(city: str) -> Optional[str]:
    """Busca clima atual de uma cidade via wttr.in."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://wttr.in/{city}?format=%C+%t+%w+%h")
            if resp.status_code == 200:
                text = resp.text.strip()
                return f"Clima em **{city}**: {text}"
            return f"Não foi possível obter o clima de {city}."
    except Exception as e:
        return f"Erro ao buscar clima: {e}"


TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Obtém o clima atual de uma cidade",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Nome da cidade (ex: São Paulo, London)",
                }
            },
            "required": ["city"],
        },
    },
}
