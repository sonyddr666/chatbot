"""Módulo de moderação de conteúdo."""

import re
from typing import Optional

# Palavras e padrões bloqueados
BLOCKED_PATTERNS = [
    r"(?i)\b(?:golpe|roubo|furto|sequestro)\b",
]

SENSITIVE_TOPICS = [
    "senha", "password", "cartão de crédito", "credit card", "cpf", "rg",
    "dados bancários", "bank details",
]


def moderate_text(text: str) -> Optional[str]:
    """Verifica se o texto contém conteúdo bloqueado.
    Retorna uma mensagem de erro se bloqueado, None se OK."""
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, text):
            return "Desculpe, não posso responder a essa solicitação."

    return None


def contains_sensitive_data(text: str) -> bool:
    """Verifica se o texto contém dados sensíveis."""
    text_lower = text.lower()
    for topic in SENSITIVE_TOPICS:
        if topic in text_lower:
            return True
    return False


async def moderate_with_api(text: str, api_key: Optional[str] = None) -> dict:
    """Moderação via OpenAI API (se disponível)."""
    if not api_key:
        return {"flagged": False, "categories": {}}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.moderations.create(input=text)
        result = response.results[0]
        return {
            "flagged": result.flagged,
            "categories": result.categories.model_dump(),
            "scores": result.category_scores.model_dump(),
        }
    except Exception:
        return {"flagged": False, "categories": {}}
