"""Suporte multilíngue para o chatbot."""

from typing import Optional
from langdetect import detect, DetectorFactory, LangDetectException

# Seed para consistência
DetectorFactory.seed = 42

# Mensagens do sistema em diferentes idiomas
WELCOME_MESSAGES = {
    "pt": "Olá! Como posso ajudar você hoje?",
    "en": "Hello! How can I help you today?",
    "es": "¡Hola! ¿Cómo puedo ayudarte hoy?",
    "fr": "Bonjour ! Comment puis-je vous aider aujourd'hui ?",
    "de": "Hallo! Wie kann ich Ihnen heute helfen?",
    "it": "Ciao! Come posso aiutarti oggi?",
    "ja": "こんにちは！今日はどのようにお手伝いできますか？",
    "zh": "你好！我今天能帮你什么？",
    "ru": "Здравствуйте! Чем я могу вам помочь сегодня?",
}

LANGUAGE_NAMES = {
    "pt": "Português",
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "it": "Italiano",
    "ja": "日本語",
    "zh": "中文",
    "ru": "Русский",
}


def detect_language(text: str) -> str:
    """Detecta o idioma do texto."""
    try:
        lang = detect(text)
        # Mapeia códigos de idioma
        if lang.startswith("zh"):
            return "zh"
        return lang
    except (LangDetectException, Exception):
        return "pt"


def get_welcome_message(lang: str) -> str:
    """Retorna mensagem de boas-vindas no idioma."""
    return WELCOME_MESSAGES.get(lang, WELCOME_MESSAGES["pt"])


def get_language_name(lang: str) -> str:
    """Retorna o nome do idioma."""
    return LANGUAGE_NAMES.get(lang, "Português")


def build_system_prompt_multilang(lang: str = "pt") -> str:
    """Constrói system prompt adaptado ao idioma."""
    base = (
        "Você é um assistente AI útil, atencioso e preciso.\n\n"
        "Diretrizes:\n"
        "- Responda de forma clara e concisa.\n"
        "- Quando não souber a resposta, admita honestamente.\n"
        "- Use o contexto fornecido para responder perguntas factuais.\n"
        "- Seja educado e mantenha um tom profissional.\n"
    )

    base += (
        "- Nunca afirme que criou, salvou, editou ou apagou um arquivo ou pasta sem um plano "
        "do Workspace confirmado como applied. Sem essa confirmacao, apresente o conteudo "
        "apenas como rascunho no chat.\n"
    )

    lang_instruction = {
        "pt": "- Responda SEMPRE em português.\n",
        "en": "- Always respond in English.\n",
        "es": "- Responda SIEMPRE en español.\n",
        "fr": "- Répondez TOUJOURS en français.\n",
        "de": "- Antworten Sie IMMER auf Deutsch.\n",
    }

    return base + lang_instruction.get(lang, "- Responda no mesmo idioma da pergunta.\n")
