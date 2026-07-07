"""Conservative preference suggestion detection.

The chatbot may notice explicit user preferences, but it only creates a
pending suggestion. Applying it still requires user confirmation.
"""

from src.db.repository import PreferenceSuggestionRepo, UserPreferenceRepo


SECRET_MARKERS = (
    "senha",
    "password",
    "token",
    "api key",
    "apikey",
    "chave de api",
    "bearer ",
    "sk-",
    "ghp_",
)


def message_may_contain_secret(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in SECRET_MARKERS)


def infer_suggestion_from_message(user_id: int, message: str) -> dict | None:
    if message_may_contain_secret(message):
        return None

    text = message.lower()
    preferences = UserPreferenceRepo.list_for_user(user_id)

    if "detalhad" in text and ("prefiro" in text or "respostas" in text or "explica" in text):
        current = preferences.get("answer_style", {}).get("value") or {}
        suggested = {**current, "detail": "detalhado"}
        if suggested == current:
            return None
        return {
            "suggestion_type": "answer_style",
            "current_value": current,
            "suggested_value": suggested,
            "reason": "Usuario indicou preferencia por respostas mais detalhadas.",
            "confidence": 0.75,
        }

    if "diret" in text and ("prefiro" in text or "seja" in text or "responda" in text):
        current = preferences.get("answer_style", {}).get("value") or {}
        suggested = {**current, "tone": "direto", "detail": "pratico"}
        if suggested == current:
            return None
        return {
            "suggestion_type": "answer_style",
            "current_value": current,
            "suggested_value": suggested,
            "reason": "Usuario indicou preferencia por respostas diretas e praticas.",
            "confidence": 0.75,
        }

    wants_english = any(term in text for term in ("ingles", "english"))
    if wants_english and ("responda" in text or "prefiro" in text or "sempre" in text):
        current = preferences.get("default_language", {}).get("value")
        if current == "en":
            return None
        return {
            "suggestion_type": "default_language",
            "current_value": current,
            "suggested_value": "en",
            "reason": "Usuario indicou preferencia por respostas em ingles.",
            "confidence": 0.7,
        }

    wants_stronger_rag = any(term in text for term in ("use sempre", "consulta sempre", "sempre usar"))
    mentions_knowledge = any(term in text for term in ("rag", "document", "base de conhecimento", "meus arquivos"))
    if wants_stronger_rag and mentions_knowledge:
        current = preferences.get("rag_aggressiveness", {}).get("value")
        if current == "high":
            return None
        return {
            "suggestion_type": "rag_aggressiveness",
            "current_value": current,
            "suggested_value": "high",
            "reason": "Usuario pediu uso mais frequente da base pessoal/documentos.",
            "confidence": 0.8,
        }

    return None


def create_suggestion_from_message(user_id: int, message: str):
    suggestion = infer_suggestion_from_message(user_id, message)
    if not suggestion:
        return None
    suggestion_type = suggestion["suggestion_type"]
    if PreferenceSuggestionRepo.has_pending(user_id, suggestion_type):
        return None
    return PreferenceSuggestionRepo.create(user_id=user_id, **suggestion)
