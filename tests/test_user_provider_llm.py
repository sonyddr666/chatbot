import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from langchain_core.messages import HumanMessage

from src.core.memory import ConversationMemory


class UserProviderLLMTest(unittest.IsolatedAsyncioTestCase):
    def test_catalog_auth_headers_use_documented_scheme(self):
        from src.core.llm import _provider_auth_headers

        self.assertEqual(
            _provider_auth_headers("secret", "bearer_api_key"),
            {"Authorization": "Bearer secret"},
        )
        self.assertEqual(
            _provider_auth_headers("secret", "x_api_key"),
            {"X-API-Key": "secret"},
        )
        self.assertEqual(
            _provider_auth_headers("secret", "authorization_api_key_scheme"),
            {"Authorization": "Api-Key secret"},
        )

    def test_anthropic_catalog_provider_uses_native_messages_adapter(self):
        from langchain_anthropic import ChatAnthropic
        from src.core.llm import get_llm

        llm = get_llm({
            "provider_id": "anthropic",
            "base_url": "https://api.anthropic.com/v1",
            "api_key": "test-anthropic-key",
            "api_format": "anthropic_messages",
            "model_id": "claude-test",
        })

        self.assertIsInstance(llm, ChatAnthropic)
        self.assertEqual(llm.model, "claude-test")

    def test_opencode_delta_preserves_reasoning_and_content(self):
        from src.core.llm import _openai_delta_parts

        parts = _openai_delta_parts({
            "reasoning_content": "analisando",
            "content": "resposta",
        })

        self.assertEqual(parts, [
            ("reasoning", "analisando"),
            ("content", "resposta"),
        ])

    def test_openrouter_reasoning_details_are_normalized(self):
        from src.core.llm import _openai_delta_parts

        parts = _openai_delta_parts({
            "reasoning_details": [
                {"type": "reasoning.text", "text": "primeiro"},
                {"type": "reasoning.encrypted", "data": "segredo"},
                {"type": "reasoning.summary", "summary": " depois"},
            ],
            "content": "resposta",
        })

        self.assertEqual(parts, [
            ("reasoning", "primeiro depois"),
            ("content", "resposta"),
        ])

    def test_content_blocks_preserve_reasoning_and_final_text(self):
        from src.core.llm import _openai_delta_parts

        parts = _openai_delta_parts({
            "content": [
                {"type": "thinking", "thinking": "planejando"},
                {"type": "text", "text": "resposta"},
            ],
        })

        self.assertEqual(parts, [
            ("reasoning", "planejando"),
            ("content", "resposta"),
        ])

    def test_analysis_field_is_treated_as_structured_reasoning(self):
        from src.core.llm import _openai_delta_parts

        self.assertEqual(
            _openai_delta_parts({"analysis": "plano", "content": "final"}),
            [("reasoning", "plano"), ("content", "final")],
        )

    def test_morph_request_enables_selected_reasoning_effort(self):
        from src.core.llm import _openai_request_variants

        variants = _openai_request_variants(
            [HumanMessage(content="oi")],
            {
                "provider_id": "morph",
                "base_url": "https://api.morphllm.com/v1",
                "model_id": "morph-dsv4flash",
            },
            response_mode="thinking",
            reasoning_effort="high",
        )

        self.assertEqual(variants[0]["reasoning"], {"effort": "high"})
        self.assertNotIn("reasoning", variants[-1])

    def test_large_buffered_content_is_split_without_data_loss(self):
        from src.core.llm import _smooth_stream_parts

        content = "abc " * 100
        parts = _smooth_stream_parts(content, chunk_size=32)

        self.assertGreater(len(parts), 1)
        self.assertEqual("".join(parts), content)

    def test_inline_thought_tag_is_split_from_final_content(self):
        from src.core.llm import _OpenAIReasoningNormalizer

        normalizer = _OpenAIReasoningNormalizer()
        parts = []
        for chunk in ("<tho", "ught>analisando", " com calma</th", "ought>Resposta final"):
            parts.extend(normalizer.feed("content", chunk))
        parts.extend(normalizer.finish())

        self.assertEqual(
            "".join(text for typ, text in parts if typ == "reasoning"),
            "analisando com calma",
        )
        self.assertEqual(
            "".join(text for typ, text in parts if typ == "content"),
            "Resposta final",
        )

    def test_inline_reasoning_supports_common_openai_compatible_tags(self):
        from src.core.llm import _OpenAIReasoningNormalizer

        for tag in ("think", "thought", "reasoning", "analysis"):
            with self.subTest(tag=tag):
                normalizer = _OpenAIReasoningNormalizer()
                parts = normalizer.feed(
                    "content",
                    f"  <{tag}>plano</{tag}>\nresposta",
                )
                parts.extend(normalizer.finish())
                self.assertEqual(parts, [
                    ("reasoning", "plano"),
                    ("content", "\nresposta"),
                ])

    def test_inline_tag_in_normal_text_is_not_reclassified(self):
        from src.core.llm import _OpenAIReasoningNormalizer

        normalizer = _OpenAIReasoningNormalizer()
        text = "Exemplo de XML: <thought>isto continua sendo texto</thought>."
        parts = normalizer.feed("content", text)
        parts.extend(normalizer.finish())

        self.assertEqual(parts, [("content", text)])

    def test_structured_reasoning_has_priority_over_inline_tags(self):
        from src.core.llm import _OpenAIReasoningNormalizer

        normalizer = _OpenAIReasoningNormalizer()
        parts = normalizer.feed("reasoning", "campo nativo")
        parts.extend(normalizer.feed("content", "<thought>texto literal</thought>resposta"))
        parts.extend(normalizer.finish())

        self.assertEqual(parts, [
            ("reasoning", "campo nativo"),
            ("content", "<thought>texto literal</thought>resposta"),
        ])

    async def test_opencode_provider_uses_direct_reasoning_stream(self):
        from src.core.llm import generate_stream

        async def fake_opencode_stream(
            messages,
            provider_config,
            response_mode="normal",
            reasoning_effort=None,
        ):
            yield ("reasoning", "analisando")
            yield ("content", provider_config["model_id"])

        provider_config = {
            "provider_id": "opencode-zen-free",
            "base_url": "https://opencode.ai/zen/v1",
            "api_key": "test-key",
            "api_format": "chat_completions",
            "model_id": "deepseek-v4-flash-free",
        }

        with patch("src.core.llm.generate_opencode_stream", new=fake_opencode_stream):
            chunks = [
                chunk
                async for chunk in generate_stream(
                    [HumanMessage(content="oi")],
                    provider_config=provider_config,
                )
            ]

        self.assertEqual(chunks, [
            ("reasoning", "analisando"),
            ("content", "deepseek-v4-flash-free"),
        ])

    async def test_generate_stream_uses_explicit_openai_compatible_config(self):
        from src.core.llm import generate_stream

        calls = []

        async def fake_compatible_stream(
            messages,
            provider_config,
            response_mode="normal",
            reasoning_effort=None,
        ):
            calls.append({
                "provider_config": provider_config,
                "response_mode": response_mode,
                "reasoning_effort": reasoning_effort,
            })
            yield ("content", f"modelo:{provider_config['model_id']}")

        provider_config = {
            "provider_id": "personal-openai",
            "base_url": "https://example.test/v1",
            "api_key": "sk-user-secret",
            "api_format": "chat_completions",
            "model_id": "user-model",
            "model_name": "User Model",
        }

        with patch(
            "src.core.llm.generate_openai_compatible_stream",
            new=fake_compatible_stream,
        ):
            chunks = [
                chunk
                async for chunk in generate_stream(
                    [HumanMessage(content="oi")],
                    provider_config=provider_config,
                    response_mode="thinking",
                    reasoning_effort="high",
                )
            ]

        self.assertEqual(chunks, [("content", "modelo:user-model")])
        self.assertEqual(calls[0]["provider_config"], provider_config)
        self.assertEqual(calls[0]["response_mode"], "thinking")
        self.assertEqual(calls[0]["reasoning_effort"], "high")

    async def test_openrouter_sse_preserves_reasoning_and_content(self):
        from src.core.llm import generate_openai_compatible_stream

        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append({
                "url": str(request.url),
                "json": json.loads(request.content),
            })
            stream = (
                ": OPENROUTER PROCESSING\n\n"
                "data: {\"choices\":[{\"delta\":{\"reasoning_details\":["
                "{\"type\":\"reasoning.text\",\"text\":\"analisando\"}]}}]}\n\n"
                "data: {\"choices\":[{\"delta\":{\"content\":\"resposta\"}}]}\n\n"
                "data: [DONE]\n\n"
            )
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=stream.encode(),
            )

        real_async_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)

        def client_factory(*args, **kwargs):
            kwargs["transport"] = transport
            return real_async_client(*args, **kwargs)

        provider_config = {
            "provider_id": "custom-router",
            "name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "test-key",
            "api_format": "chat_completions",
            "model_id": "deepseek/deepseek-r1",
        }
        with patch("src.core.llm.httpx.AsyncClient", new=client_factory):
            chunks = [
                chunk
                async for chunk in generate_openai_compatible_stream(
                    [HumanMessage(content="oi")],
                    provider_config,
                    response_mode="thinking",
                    reasoning_effort="high",
                )
            ]

        self.assertEqual(chunks, [
            ("reasoning", "analisando"),
            ("content", "resposta"),
        ])
        self.assertEqual(requests[0]["url"], "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(requests[0]["json"]["reasoning"], {"effort": "high"})

    async def test_unknown_provider_splits_inline_thought_from_sse_content(self):
        from src.core.llm import generate_openai_compatible_stream

        def handler(request: httpx.Request) -> httpx.Response:
            stream = (
                'data: {"choices":[{"delta":{"content":"<tho"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"ught>planejando</th"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"ought>Olá!"}}]}\n\n'
                "data: [DONE]\n\n"
            )
            return httpx.Response(200, content=stream.encode())

        real_async_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)

        def client_factory(*args, **kwargs):
            kwargs["transport"] = transport
            return real_async_client(*args, **kwargs)

        with patch("src.core.llm.httpx.AsyncClient", new=client_factory):
            chunks = [
                chunk
                async for chunk in generate_openai_compatible_stream(
                    [HumanMessage(content="oi")],
                    {
                        "provider_id": "google-ai-studio-manual",
                        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                        "api_key": "test-key",
                        "api_format": "chat_completions",
                        "model_id": "gemma-test",
                    },
                )
            ]

        self.assertEqual("".join(t for typ, t in chunks if typ == "reasoning"), "planejando")
        self.assertEqual("".join(t for typ, t in chunks if typ == "content"), "Olá!")

    async def test_unknown_provider_omits_unverified_reasoning_fields(self):
        from src.core.llm import generate_openai_compatible_stream

        payloads = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            payloads.append(payload)
            stream = (
                "data: {\"choices\":[{\"delta\":{\"reasoning\":\"pensando\"}}]}\n\n"
                "data: {\"choices\":[{\"delta\":{\"content\":\"ok\"}}]}\n\n"
                "data: [DONE]\n\n"
            )
            return httpx.Response(200, content=stream.encode())

        real_async_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)

        def client_factory(*args, **kwargs):
            kwargs["transport"] = transport
            return real_async_client(*args, **kwargs)

        with patch("src.core.llm.httpx.AsyncClient", new=client_factory):
            chunks = [
                chunk
                async for chunk in generate_openai_compatible_stream(
                    [HumanMessage(content="oi")],
                    {
                        "provider_id": "unknown",
                        "base_url": "https://unknown.example/v1",
                        "api_key": "test-key",
                        "api_format": "chat_completions",
                        "model_id": "unknown-model",
                    },
                    response_mode="thinking",
                    reasoning_effort="medium",
                )
            ]

        self.assertEqual(chunks, [
            ("reasoning", "pensando"),
            ("content", "ok"),
        ])
        self.assertEqual(len(payloads), 1)
        self.assertNotIn("reasoning", payloads[0])
        self.assertNotIn("reasoning_effort", payloads[0])

    def test_groq_qwen_uses_binary_reasoning_contract(self):
        from src.core.llm import _openai_request_variants

        variants = _openai_request_variants(
            [HumanMessage(content="oi")],
            {
                "provider_id": "groq",
                "base_url": "https://api.groq.com/openai/v1",
                "model_id": "qwen/qwen3-32b",
                "reasoning_style": "reasoning_effort",
                "supports_thinking": True,
            },
            response_mode="thinking",
            reasoning_effort="low",
        )

        self.assertEqual(variants[0]["reasoning_effort"], "default")
        self.assertEqual(variants[0]["reasoning_format"], "parsed")

    def test_groq_gpt_oss_clamps_reasoning_to_supported_scale(self):
        from src.core.llm import _openai_request_variants

        variants = _openai_request_variants(
            [HumanMessage(content="oi")],
            {
                "provider_id": "groq",
                "base_url": "https://api.groq.com/openai/v1",
                "model_id": "openai/gpt-oss-120b",
                "reasoning_style": "reasoning_effort",
                "supports_thinking": True,
            },
            response_mode="thinking",
            reasoning_effort="max",
        )

        self.assertEqual(variants[0]["reasoning_effort"], "high")

    def test_openai_payload_omits_unsupported_temperature(self):
        from src.core.llm import _openai_request_variants

        variants = _openai_request_variants(
            [HumanMessage(content="oi")],
            {
                "provider_id": "example",
                "base_url": "https://example.test/v1",
                "model_id": "fixed-temperature-model",
                "supports_temperature": False,
            },
            response_mode="normal",
            reasoning_effort=None,
        )

        self.assertNotIn("temperature", variants[0])

    async def test_cloudflare_placeholder_attempts_account_discovery(self):
        from src.core.llm import generate_openai_compatible_stream

        with patch(
            "src.core.cloudflare_provider.discover_cloudflare_accounts",
            new=AsyncMock(return_value=[]),
        ) as discover:
            with self.assertRaisesRegex(RuntimeError, "nenhuma conta"):
                async for _ in generate_openai_compatible_stream(
                    [HumanMessage(content="oi")],
                    {
                        "provider_id": "cloudflare-workers-ai",
                        "name": "Cloudflare Workers AI",
                        "base_url": "https://api.cloudflare.com/client/v4/accounts/COLOQUE_SEU_ACCOUNT_ID/ai/v1",
                        "model_id": "@cf/openai/gpt-oss-120b",
                        "api_key": "test-key",
                    },
                ):
                    pass
        discover.assert_awaited_once_with("test-key")

    async def test_cloudflare_single_account_replaces_placeholder(self):
        from src.core.llm import resolve_provider_config

        config = {
            "provider_id": "cloudflare-workers-ai",
            "name": "Cloudflare Workers AI",
            "base_url": "https://api.cloudflare.com/client/v4/accounts/COLOQUE_SEU_ACCOUNT_ID/ai/v1",
            "api_key": "test-key",
        }
        with (
            patch(
                "src.core.cloudflare_provider.discover_cloudflare_accounts",
                new=AsyncMock(return_value=[{"id": "a1b2c3d4", "name": "Pessoal"}]),
            ),
            patch("src.core.provider_manager.update_provider") as update,
        ):
            resolved = await resolve_provider_config(config)

        expected = "https://api.cloudflare.com/client/v4/accounts/a1b2c3d4/ai/v1"
        self.assertEqual(resolved["base_url"], expected)
        update.assert_called_once_with("cloudflare-workers-ai", {"base_url": expected})

    async def test_chat_engine_passes_provider_config_to_generate_stream(self):
        from src.core.chat import ChatEngine

        seen = []

        async def fake_generate_stream(
            messages,
            provider_config=None,
            response_mode="normal",
            reasoning_effort=None,
        ):
            seen.append({
                "provider_config": provider_config,
                "response_mode": response_mode,
                "reasoning_effort": reasoning_effort,
            })
            yield ("content", provider_config["model_id"])

        provider_config = {"model_id": "user-model"}
        memory = ConversationMemory()

        with patch("src.core.chat.generate_stream", new=fake_generate_stream):
            engine = ChatEngine(memory, provider_config=provider_config)
            response = await engine.chat("ola")

        self.assertEqual(response, "user-model")
        self.assertEqual(seen, [{
            "provider_config": provider_config,
            "response_mode": "normal",
            "reasoning_effort": None,
        }])


if __name__ == "__main__":
    unittest.main()
