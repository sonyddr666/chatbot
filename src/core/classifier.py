"""Classificador de rota - decide se uma mensagem precisa de processamento completo ou pode ir pela rota rápida.

Regras:
- Rota rápida: sem RAG, sem thinking, modelo leve
- Rota completa: RAG + thinking + modelo completo
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

RouteType = Literal["fast", "full"]


SEARCH_TOOLS = {"web_search", "perplexo_search", "simple_search", "search_and_answer"}
WORKSPACE_TOOLS = {"workspace_search", "workspace_list", "workspace_read", "workspace_grep"}
IMAGE_TOOLS = {"image_generate", "image_edit"}


@dataclass(frozen=True)
class ToolRoute:
    """Local, deterministic capability filter applied before any planner call."""

    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    requested_categories: frozenset[str] = field(default_factory=frozenset)
    terminal_tool: str = ""
    compound: bool = False


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def classify_tool_route(message: str, attachments: list[dict] | None = None) -> ToolRoute:
    """Return only capabilities explicitly justified by the complete request."""
    text = _plain(message)
    allowed: set[str] = set()
    categories: set[str] = set()
    terminal = ""

    local_search = bool(re.search(
        r"\b(pesquis\w*|busc\w*|procur\w*)\b.*\b(dentro do (?:sistema|workspace)|meus? arquivos?|minhas? pastas?)\b",
        text,
    ))
    wants_search = bool(re.search(r"\b(pesquis\w*|busc\w*|procur\w*|internet|web)\b", text)) and not local_search
    wants_history = bool(re.search(r"\b(historico|conversas? anteriores?|outros? chats?|lembra\w*)\b", text))
    wants_workspace = local_search or bool(re.search(r"\b(arquivos?|pastas?|workspace|diretorio)\b", text))
    if not wants_workspace and re.search(r"\b(leia|abra|busque|procure|liste)\b.*\bprojeto\b", text):
        wants_workspace = True
    wants_list = bool(re.search(r"\b(list\w*|mostr\w*|quais|estrutura)\b", text)) and wants_workspace
    wants_file_delivery = bool(re.search(r"\b(envi\w*|mand\w*|entreg\w*|baix\w*)\b", text)) and wants_workspace
    wants_time = bool(re.search(r"\b(que horas|qual (?:e )?a hora|que dia|data (?:de )?hoje|agora)\b", text))
    wants_weather = bool(re.search(r"\b(clima|tempo em|previsao do tempo|temperatura)\b", text))
    wants_url = "http://" in text or "https://" in text or bool(re.search(r"\b(url|site|pagina web|link)\b", text))
    wants_calculation = bool(re.search(r"\b(calcule|calcular|conta|somar|multiplicar|porcentagem)\b", text))
    wants_rag = bool(re.search(r"\b(rag|base de conhecimento|documentos indexados)\b", text))
    wants_schedule = bool(re.search(r"\b(agend\w*|lembre-me|daqui a \d+|amanha as|tarefa futura)\b", text))

    # Image intent uses the same conservative detector as the durable job path.
    from src.core.image_actions import detect_image_action
    image_action = detect_image_action(message, attachments or [])
    if image_action:
        terminal = "image_edit" if image_action.get("operation") == "edit" else "image_generate"
        allowed.add(terminal)
        categories.add("image")
    if wants_search:
        allowed.update(SEARCH_TOOLS)
        categories.add("search")
    if wants_history:
        allowed.add("conversation_history")
        categories.add("history")
    if wants_workspace:
        allowed.update({"workspace_search", "workspace_read", "workspace_grep"})
        categories.add("workspace")
        if wants_list:
            allowed.add("workspace_list")
    if wants_file_delivery:
        allowed.add("file_delivery")
        categories.add("file_delivery")
    if wants_time:
        allowed.add("get_time")
        categories.add("time")
    if wants_weather:
        allowed.add("get_weather")
        categories.add("weather")
    if wants_url:
        allowed.add("read_url_content")
        categories.add("url")
    if wants_calculation:
        allowed.add("calculate")
        categories.add("calculation")
    if wants_rag:
        allowed.add("rag_search")
        categories.add("rag")
    if wants_schedule:
        allowed.update({"schedule_task", "list_schedules", "cancel_schedule"})
        categories.add("schedule")

    # A request is compound when it genuinely needs more than one capability category.
    return ToolRoute(
        allowed_tools=frozenset(allowed),
        requested_categories=frozenset(categories),
        terminal_tool=terminal,
        compound=len(categories) > 1,
    )

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
