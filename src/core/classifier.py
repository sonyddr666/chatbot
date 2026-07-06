"""Classificador de rota - decide se uma mensagem precisa de processamento completo ou pode ir pela rota rápida.

Regras:
- Rota rápida: sem RAG, sem thinking, modelo leve
- Rota completa: RAG + thinking + modelo completo
"""

import re
from typing import Literal

RouteType = Literal["fast", "full"]

# Palavras que indicam pergunta complexa (precisa de rota completa)
COMPLEX_PATTERNS = [
    r"explique\s+em\s+detalhes",
    r"compare\s+",
    r"diferença\s+entre",
    r"vantagens?\s+e\s+desvantagens?",
    r"como\s+funciona",
    r"o\s+que\s+é\s+",
    r"qual\s+a\s+diferença",
    r"pode\s+me\s+explicar",
    r"resuma\s+",
    r"analise\s+",
    r"o\s+que\s+significa",
    r"por\s+que\s+",
    r"como\s+resolver",
    r"preciso\s+de\s+ajuda\s+com",
    r"documento",
    r"base\s+de\s+conhecimento",
    r"arquivo",
]

# Saudações e mensagens simples (rota rápida)
FAST_PATTERNS = [
    r"^oi",
    r"^ola",
    r"^olá",
    r"^bom\s+dia",
    r"^boa\s+tarde",
    r"^boa\s+noite",
    r"^tudo\s+bem",
    r"^hey",
    r"^hello",
    r"^hi",
    r"^valeu",
    r"^obrigado",
    r"^brigado",
    r"^thanks",
    r"^tks",
    r"^sim$",
    r"^não$",
    r"^nao$",
    r"^ok$",
    r"^blz$",
    r"^legal$",
    r"^show$",
    r"^entendi",
    r"^compreendi",
    r"^$",
]

# Mensagens muito curtas sem "?" são provavelmente rápidas
def _is_very_short(message: str) -> bool:
    """Mensagens com menos de 3 palavras e sem pontuação complexa."""
    words = message.strip().split()
    if len(words) <= 2:
        return True
    return False


def classify_route(message: str) -> RouteType:
    """Classifica a mensagem em rota rápida ou completa.

    Args:
        message: Texto da mensagem do usuário.

    Returns:
        "fast" para rota rápida (sem RAG/thinking),
        "full" para rota completa (RAG + thinking).
    """
    msg_lower = message.strip().lower()

    # Se for saudação ou muito curta → rápida
    for pattern in FAST_PATTERNS:
        if re.match(pattern, msg_lower):
            return "fast"

    if _is_very_short(msg_lower):
        return "fast"

    # Se tiver patterns complexos → completa
    for pattern in COMPLEX_PATTERNS:
        if re.search(pattern, msg_lower):
            return "full"

    # Se tiver "?" e mais de 5 palavras → completa
    if "?" in message and len(message.split()) > 5:
        return "full"

    # Default: rápida (70% das mensagens caem aqui)
    return "fast"
