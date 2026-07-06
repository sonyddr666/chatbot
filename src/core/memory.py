"""Gerenciamento de memória de curto prazo (histórico da conversa)."""

from typing import Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from src.core.prompts import build_system_prompt


class ConversationMemory:
    """Mantém o histórico da conversa para uma sessão."""

    def __init__(self, max_turns: int = 20, system_prompt: Optional[str] = None):
        self.max_turns = max_turns
        self.system_prompt = system_prompt or build_system_prompt()
        self.messages: list[BaseMessage] = [SystemMessage(content=self.system_prompt)]

    def add_user_message(self, content: str) -> None:
        self.messages.append(HumanMessage(content=content))

    def add_ai_message(self, content: str) -> None:
        self.messages.append(AIMessage(content=content))

    def get_messages(self) -> list[BaseMessage]:
        """Retorna as mensagens respeitando o limite de turns."""
        # Sempre inclui o system prompt
        msgs = [self.messages[0]]
        # Pega os últimos N turns (cada turn = user + ai)
        recent = self.messages[1:]
        if len(recent) > self.max_turns * 2:
            recent = recent[-(self.max_turns * 2):]
        msgs.extend(recent)
        return msgs

    def update_system_prompt(self, context: Optional[str] = None) -> None:
        """Atualiza o system prompt (ex: após busca RAG)."""
        self.messages[0] = SystemMessage(content=build_system_prompt(context))

    def clear(self) -> None:
        """Limpa o histórico (mantém apenas o system prompt)."""
        self.messages = [self.messages[0]]


# Cache global de sessões (para uso em memória)
_sessions: dict[str, ConversationMemory] = {}


def _load_history_from_db(session_id: str, memory: ConversationMemory) -> None:
    """Reidrata memória RAM com histórico persistido após restart do servidor."""
    try:
        from src.db.repository import ConversationRepo
        history = ConversationRepo.get_history(session_id, limit=memory.max_turns * 2)
        for msg in history:
            if msg.role == "user":
                memory.messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                memory.messages.append(AIMessage(content=msg.content))
    except Exception:
        # Se DB ainda não estiver pronto, segue com memória vazia.
        pass


def get_session(session_id: str) -> ConversationMemory:
    """Recupera ou cria uma sessão."""
    if session_id not in _sessions:
        memory = ConversationMemory()
        _load_history_from_db(session_id, memory)
        _sessions[session_id] = memory
    return _sessions[session_id]
