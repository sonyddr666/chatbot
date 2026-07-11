"""Lógica principal do loop de conversa do chatbot.
Suporta streaming com separação de reasoning e content.
"""

from typing import AsyncGenerator, Tuple

from src.core.llm import generate_stream
from src.core.memory import ConversationMemory


class ChatEngine:
    """Motor de conversa que orquestra LLM + memória."""

    def __init__(
        self,
        memory: ConversationMemory,
        provider_config: dict | None = None,
        response_mode: str = "normal",
        reasoning_effort: str | None = None,
    ):
        self.memory = memory
        self.provider_config = provider_config
        self.response_mode = response_mode
        self.reasoning_effort = reasoning_effort

    async def chat_stream(
        self, user_input: str
    ) -> AsyncGenerator[Tuple[str, str], None]:
        """Processa mensagem e retorna streaming com reasoning + content.

        Yields:
            Tuplas (tipo, texto):
            - ("reasoning", str) → pensamento interno
            - ("content", str)   → resposta final
        """
        self.memory.add_user_message(user_input)
        messages = self.memory.get_messages()

        full_reasoning_parts: list[str] = []
        full_content_parts: list[str] = []

        async for typ, text in generate_stream(
            messages,
            provider_config=self.provider_config,
            response_mode=self.response_mode,
            reasoning_effort=self.reasoning_effort,
        ):
            if typ == "error":
                raise RuntimeError(text)
            if typ == "reasoning":
                full_reasoning_parts.append(text)
            else:
                full_content_parts.append(text)
            yield (typ, text)

        full_reasoning = "".join(full_reasoning_parts)
        full_content = "".join(full_content_parts)

        # Salva no histórico (só o content, reasoning é efêmero)
        if full_content:
            self.memory.add_ai_message(full_content)

    async def chat(self, user_input: str) -> str:
        """Processa uma mensagem e retorna a resposta completa."""
        full_content = ""
        async for typ, text in self.chat_stream(user_input):
            if typ == "content":
                full_content += text
        return full_content
