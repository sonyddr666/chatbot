"""Testes do núcleo do chatbot."""

import pytest
from unittest.mock import patch
from src.core.memory import ConversationMemory
from src.core.chat import ChatEngine
from src.core.prompts import build_system_prompt


class TestPrompts:
    def test_build_system_prompt_sem_contexto(self):
        prompt = build_system_prompt()
        assert "Você é um assistente AI" in prompt
        assert "Contexto relevante" not in prompt

    def test_build_system_prompt_com_contexto(self):
        prompt = build_system_prompt(context="Texto de teste")
        assert "Contexto relevante" in prompt
        assert "Texto de teste" in prompt


class TestMemory:
    def test_cria_memoria_vazia(self):
        mem = ConversationMemory()
        msgs = mem.get_messages()
        assert len(msgs) == 1  # só o system prompt
        assert msgs[0].type == "system"

    def test_adiciona_mensagens(self):
        mem = ConversationMemory()
        mem.add_user_message("Olá")
        mem.add_ai_message("Oi!")
        msgs = mem.get_messages()
        assert len(msgs) == 3  # system + user + ai

    def test_respeita_limite_de_turns(self):
        mem = ConversationMemory(max_turns=2)
        mem.add_user_message("1")
        mem.add_ai_message("R1")
        mem.add_user_message("2")
        mem.add_ai_message("R2")
        mem.add_user_message("3")
        mem.add_ai_message("R3")

        msgs = mem.get_messages()
        # system + 2 últimos turns (4 mensagens)
        assert len(msgs) == 5

    def test_clear(self):
        mem = ConversationMemory()
        mem.add_user_message("Olá")
        mem.clear()
        msgs = mem.get_messages()
        assert len(msgs) == 1  # só o system prompt

    def test_update_system_prompt(self):
        mem = ConversationMemory()
        mem.update_system_prompt(context="Novo contexto")
        assert "Novo contexto" in mem.messages[0].content


class TestChatEngine:
    @pytest.mark.asyncio
    async def test_chat_adiciona_ao_historico(self):
        """Teste básico de fluxo (sem chamar LLM de verdade)."""
        mem = ConversationMemory()
        engine = ChatEngine(mem)

        # O método chat_stream tenta chamar LLM, então este teste
        # precisaria de mock. Por enquanto é um placeholder.
        assert engine.memory is mem
        assert len(mem.get_messages()) == 1

    @pytest.mark.asyncio
    async def test_fallback_uses_only_another_provider_with_same_model(self):
        calls = []

        async def fake_generate(_messages, provider_config, **_kwargs):
            calls.append(provider_config["provider_id"])
            if provider_config["provider_id"] == "primary":
                raise RuntimeError("upstream failed")
            yield "content", "ok"

        engine = ChatEngine(
            ConversationMemory(),
            {"provider_id": "primary", "name": "Primary", "model_id": "same-model"},
        )
        with patch("src.core.chat.generate_stream", new=fake_generate):
            chunks = [item async for item in engine.chat_stream_with_fallback("oi", [
                {"provider_id": "wrong", "model_id": "other-model"},
                {"provider_id": "backup", "name": "Backup", "model_id": "same-model"},
            ])]

        assert calls == ["primary", "backup"]
        assert chunks == [("content", "ok")]
        assert engine.provider_config["provider_id"] == "backup"

    @pytest.mark.asyncio
    async def test_fallback_does_not_mix_response_after_first_token(self):
        calls = []

        async def fake_generate(_messages, provider_config, **_kwargs):
            calls.append(provider_config["provider_id"])
            yield "content", "parcial"
            raise RuntimeError("stream caiu")

        engine = ChatEngine(
            ConversationMemory(),
            {"provider_id": "primary", "name": "Primary", "model_id": "same-model"},
        )
        chunks = []
        with patch("src.core.chat.generate_stream", new=fake_generate):
            with pytest.raises(RuntimeError):
                async for item in engine.chat_stream_with_fallback("oi", [
                    {"provider_id": "backup", "model_id": "same-model"},
                ]):
                    chunks.append(item)

        assert calls == ["primary"]
        assert chunks == [("content", "parcial")]
