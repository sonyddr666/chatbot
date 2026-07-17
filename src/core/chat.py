"""Main conversation loop with streaming and same-model provider fallback."""

import inspect
from typing import Any, AsyncGenerator, Awaitable, Callable, Tuple

from src.core.llm import generate_stream
from src.core.memory import ConversationMemory


class ChatEngine:
    """Conversation engine that orchestrates the LLM and in-memory history."""

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
        self, user_input: str | list[dict[str, Any]]
    ) -> AsyncGenerator[Tuple[str, str], None]:
        async for item in self.chat_stream_with_fallback(user_input, []):
            yield item

    async def chat_stream_with_fallback(
        self,
        user_input: str | list[dict[str, Any]],
        fallback_provider_configs: list[dict],
        on_fallback: Callable[[dict, dict, Exception], Awaitable[None] | None] | None = None,
    ) -> AsyncGenerator[Tuple[str, str], None]:
        """Fail over before output, and never change the requested model id."""
        primary = self.provider_config or {}
        model_id = str(primary.get("model_id") or "")
        candidates = [primary] + [
            config for config in fallback_provider_configs
            if str(config.get("model_id") or "") == model_id
        ]
        self.memory.add_user_message(user_input)
        messages = self.memory.get_messages()
        errors: list[str] = []

        for index, config in enumerate(candidates):
            full_content_parts: list[str] = []
            emitted = False
            try:
                async for typ, text in generate_stream(
                    messages,
                    provider_config=config,
                    response_mode=self.response_mode,
                    reasoning_effort=self.reasoning_effort,
                ):
                    if typ == "error":
                        raise RuntimeError(text)
                    emitted = True
                    if typ != "reasoning":
                        full_content_parts.append(text)
                    yield typ, text
                self.provider_config = config
                full_content = "".join(full_content_parts)
                if full_content:
                    self.memory.add_ai_message(full_content)
                return
            except Exception as exc:
                provider_name = str(config.get("name") or config.get("provider_id") or "provider")
                errors.append(f"{provider_name}: {exc}")
                if emitted or index + 1 >= len(candidates):
                    raise RuntimeError(" | ".join(errors)) from exc
                if on_fallback:
                    result = on_fallback(config, candidates[index + 1], exc)
                    if inspect.isawaitable(result):
                        await result

    async def chat(self, user_input: str | list[dict[str, Any]]) -> str:
        full_content = ""
        async for typ, text in self.chat_stream(user_input):
            if typ == "content":
                full_content += text
        return full_content
