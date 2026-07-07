import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessageChunk, HumanMessage

from src.core.memory import ConversationMemory


class FakeStreamingLLM:
    def __init__(self, calls: list[dict], **kwargs):
        self.calls = calls
        self.kwargs = kwargs
        self.calls.append(kwargs)

    async def astream(self, messages):
        yield AIMessageChunk(content=f"modelo:{self.kwargs['model']}")


class UserProviderLLMTest(unittest.IsolatedAsyncioTestCase):
    async def test_generate_stream_uses_explicit_provider_config(self):
        from src.core.llm import generate_stream

        calls = []

        def fake_chat_openai(**kwargs):
            return FakeStreamingLLM(calls, **kwargs)

        provider_config = {
            "provider_id": "personal-openai",
            "base_url": "https://example.test/v1",
            "api_key": "sk-user-secret",
            "api_format": "chat_completions",
            "model_id": "user-model",
            "model_name": "User Model",
        }

        with patch("src.core.llm.ChatOpenAI", new=fake_chat_openai):
            chunks = [
                chunk
                async for chunk in generate_stream(
                    [HumanMessage(content="oi")],
                    provider_config=provider_config,
                )
            ]

        self.assertEqual(chunks, [("content", "modelo:user-model")])
        self.assertEqual(calls[0]["model"], "user-model")
        self.assertEqual(calls[0]["base_url"], "https://example.test/v1")
        self.assertEqual(calls[0]["api_key"], "sk-user-secret")

    async def test_chat_engine_passes_provider_config_to_generate_stream(self):
        from src.core.chat import ChatEngine

        seen = []

        async def fake_generate_stream(messages, provider_config=None):
            seen.append(provider_config)
            yield ("content", provider_config["model_id"])

        provider_config = {"model_id": "user-model"}
        memory = ConversationMemory()

        with patch("src.core.chat.generate_stream", new=fake_generate_stream):
            engine = ChatEngine(memory, provider_config=provider_config)
            response = await engine.chat("ola")

        self.assertEqual(response, "user-model")
        self.assertEqual(seen, [provider_config])


if __name__ == "__main__":
    unittest.main()
