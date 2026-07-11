"""Search a user's persisted conversations without crossing user boundaries."""

from __future__ import annotations

import re
import unicodedata

from src.db.models import Conversation, Message, get_session_db


MAX_SCANNED_MESSAGES = 1000
MAX_SNIPPET_CHARS = 900
HISTORY_STOPWORDS = {
    "a", "agora", "algum", "alguma", "as", "chat", "chats", "com", "conversa",
    "conversas", "da", "das", "dados", "de", "disse", "do", "dos", "e", "em",
    "eu", "falei", "historico", "history", "leia", "lembra", "ler", "mensagem", "mensagens", "meu",
    "meus", "minha", "minhas", "na", "nas", "no", "nos", "o", "outra", "outras",
    "outro", "outros", "para", "pesquise", "procure", "que", "sobre", "todas", "todos",
    "voce",
}


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _keywords(query: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9_.-]+", _fold(query))
    result: list[str] = []
    for word in words:
        if word in HISTORY_STOPWORDS or word in result:
            continue
        result.append(word)
    return result[:12]


def _snippet(value: str) -> str:
    clean = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(clean) <= MAX_SNIPPET_CHARS:
        return clean
    return clean[:MAX_SNIPPET_CHARS].rstrip() + "..."


def search_conversation_history(
    user_id: int,
    query: str,
    exclude_session_id: str | None = None,
    max_conversations: int = 5,
    max_messages: int = 12,
) -> dict:
    """Return ranked excerpts from this user's other persisted conversations."""
    max_conversations = min(max(int(max_conversations), 1), 10)
    max_messages = min(max(int(max_messages), 1), 24)
    terms = _keywords(query)
    db = get_session_db()
    try:
        rows_query = (
            db.query(Message, Conversation)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(
                Conversation.user_id == user_id,
                Message.content != "",
            )
        )
        if exclude_session_id:
            rows_query = rows_query.filter(Conversation.session_id != exclude_session_id)
        rows = (
            rows_query
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(MAX_SCANNED_MESSAGES)
            .all()
        )

        candidates: list[dict] = []
        for recency, (message, conversation) in enumerate(rows):
            content_folded = _fold(message.content)
            title_folded = _fold(conversation.title)
            matched = [term for term in terms if term in content_folded or term in title_folded]
            if terms and not matched:
                continue
            score = 1
            if terms:
                score += len(set(matched)) * 10
                score += sum(min(content_folded.count(term), 4) for term in matched)
                score += sum(4 for term in matched if term in title_folded)
            candidates.append({
                "message": message,
                "conversation": conversation,
                "score": score,
                "recency": recency,
            })

        candidates.sort(key=lambda item: (item["score"], -item["recency"]), reverse=True)
        selected: list[dict] = []
        selected_conversations: set[int] = set()
        per_conversation: dict[int, int] = {}
        for candidate in candidates:
            conversation_id = int(candidate["conversation"].id)
            if conversation_id not in selected_conversations and len(selected_conversations) >= max_conversations:
                continue
            if per_conversation.get(conversation_id, 0) >= 4:
                continue
            selected.append(candidate)
            selected_conversations.add(conversation_id)
            per_conversation[conversation_id] = per_conversation.get(conversation_id, 0) + 1
            if len(selected) >= max_messages:
                break

        if not selected:
            return {
                "context": "Nenhuma mensagem relevante foi encontrada nas outras conversas deste usuario.",
                "conversation_count": 0,
                "message_count": 0,
                "titles": [],
                "terms": terms,
            }

        grouped: dict[int, dict] = {}
        for item in selected:
            conversation = item["conversation"]
            message = item["message"]
            group = grouped.setdefault(int(conversation.id), {
                "title": conversation.title or "Conversa sem titulo",
                "updated_at": conversation.updated_at,
                "messages": [],
            })
            group["messages"].append(message)

        lines = [
            "Trechos encontrados no historico privado de conversas deste usuario.",
            f"Conversas selecionadas: {len(grouped)}; mensagens selecionadas: {len(selected)}.",
        ]
        if terms:
            lines.append("Termos usados na busca: " + ", ".join(terms) + ".")
        for group in grouped.values():
            updated_at = group["updated_at"].isoformat() if group["updated_at"] else "data desconhecida"
            lines.append(f"\n## {group['title']} ({updated_at})")
            for message in sorted(group["messages"], key=lambda item: (item.created_at, item.id)):
                role = "Usuario" if message.role == "user" else "Assistente"
                lines.append(f"- {role}: {_snippet(message.content)}")

        return {
            "context": "\n".join(lines),
            "conversation_count": len(grouped),
            "message_count": len(selected),
            "titles": [group["title"] for group in grouped.values()],
            "terms": terms,
        }
    finally:
        db.close()
