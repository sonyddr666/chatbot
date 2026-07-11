"""Interface unificada para múltiplos provedores de LLM.
Suporta OpenAI, Anthropic, Ollama, Codex ChatGPT e qualquer API compatível com OpenAI.
Gera streaming com separação de reasoning_content e content.
"""

import asyncio
import json
from typing import AsyncGenerator, Tuple, Optional
import httpx
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessageChunk, HumanMessage, SystemMessage

from src.config import settings
from src.core.provider_manager import get_active_config
from src.core.account_pool import get_best_account, fetch_codex_quota
from src.core.codex_client import chat_completion_stream
from src.core.response_modes import (
    CODEX_MODE_PROFILES,
    codex_wire_reasoning_effort,
    normalize_reasoning_effort,
    normalize_response_mode,
)


def _is_codex_provider(provider_id: str) -> bool:
    return provider_id == "codex-chatgpt"


def _is_opencode_provider(config: dict) -> bool:
    provider_id = str(config.get("provider_id", "")).lower()
    base_url = str(config.get("base_url", "")).lower()
    return provider_id.startswith("opencode-") or "opencode.ai/" in base_url


def _coerce_stream_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_coerce_stream_text(item) for item in value)
    if isinstance(value, dict):
        for key in ("text", "content", "reasoning_content", "reasoning", "thinking"):
            if key in value:
                return _coerce_stream_text(value[key])
    return ""


def _openai_delta_parts(delta: dict) -> list[tuple[str, str]]:
    """Normalize common reasoning fields used by OpenAI-compatible gateways."""
    parts: list[tuple[str, str]] = []
    for key in ("reasoning_content", "reasoning", "thinking"):
        reasoning = _coerce_stream_text(delta.get(key))
        if reasoning:
            parts.append(("reasoning", reasoning))
            break
    content = _coerce_stream_text(delta.get("content"))
    if content:
        parts.append(("content", content))
    return parts


def _smooth_stream_parts(text: str, chunk_size: int = 48) -> list[str]:
    """Avoid dropping a complete buffered answer into the UI in one frame."""
    if len(text) <= chunk_size * 2:
        return [text]
    return [text[index:index + chunk_size] for index in range(0, len(text), chunk_size)]


def _messages_for_openai(messages: list[BaseMessage]) -> list[dict]:
    result = []
    for message in messages:
        if isinstance(message, SystemMessage):
            role = "system"
        elif isinstance(message, HumanMessage):
            role = "user"
        else:
            role = "assistant"
        result.append({"role": role, "content": message.content})
    return result


async def generate_opencode_stream(
    messages: list[BaseMessage],
    provider_config: dict,
) -> AsyncGenerator[Tuple[str, str], None]:
    """Read OpenCode SSE directly so non-standard reasoning fields are preserved."""
    base_url = str(provider_config.get("base_url", "")).rstrip("/")
    model = str(provider_config.get("model_id", "")).strip()
    api_key = str(provider_config.get("api_key", "")).strip()
    if not base_url or not model or not api_key:
        raise RuntimeError("Provider OpenCode incompleto: URL, modelo ou chave ausente")

    endpoint = base_url if base_url.endswith("/chat/completions") else base_url + "/chat/completions"
    payload = {
        "model": model,
        "messages": _messages_for_openai(messages),
        "stream": True,
        "temperature": 0.7,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
    }
    received_text = False
    pending_type = ""
    pending_text = ""
    timeout = httpx.Timeout(120.0, connect=10.0)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
            if response.status_code >= 400:
                detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"OpenCode retornou HTTP {response.status_code}: {detail}")

            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if event.get("error"):
                    raise RuntimeError(f"OpenCode retornou erro: {event['error']}")
                for choice in event.get("choices") or []:
                    delta = choice.get("delta") or choice.get("message") or {}
                    for typ, text in _openai_delta_parts(delta):
                        received_text = True
                        if pending_type and pending_type != typ and pending_text:
                            for piece in _smooth_stream_parts(pending_text):
                                yield (pending_type, piece)
                            pending_text = ""
                        pending_type = typ
                        pending_text += text
                        if len(pending_text) >= 24 or "\n" in text:
                            pieces = _smooth_stream_parts(pending_text)
                            for index, piece in enumerate(pieces):
                                yield (pending_type, piece)
                                if len(pieces) > 1 and index < len(pieces) - 1:
                                    await asyncio.sleep(0.004)
                            pending_text = ""

    if pending_type and pending_text:
        for piece in _smooth_stream_parts(pending_text):
            yield (pending_type, piece)

    if not received_text:
        raise RuntimeError("OpenCode encerrou o stream sem conteudo")


def _convert_messages_to_codex(messages: list[BaseMessage]) -> list[dict]:
    """Converte mensagens LangChain pro formato da API do ChatGPT."""
    result = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            role = "system"
        elif isinstance(msg, HumanMessage):
            role = "user"
        else:
            role = "assistant"
        
        content = msg.content
        if isinstance(content, list):
            # Multi-modal: extrai texto
            texts = [p.get("text", "") for p in content if isinstance(p, dict)]
            content = "\n".join(texts)
        
        result.append({"role": role, "content": str(content)})
    return result


async def get_codex_account() -> Optional[dict]:
    """Retorna a melhor conta Codex disponível."""
    return await get_best_account("codex-chatgpt")


def get_llm(provider_config: dict | None = None) -> BaseChatModel:
    """Retorna o modelo de LLM configurado.
    
    NOTA: Para Codex ChatGPT, NÃO use esta função diretamente.
    Use get_codex_account() + generate_codex_stream() em vez disso.
    
    Prioridade:
    1. Provider manager
    2. Settings / .env (fallback)
    """
    pm_cfg = provider_config or get_active_config()
    
    # Se for Codex, retorna None — o chat.py lida separadamente
    if _is_codex_provider(pm_cfg.get("provider_id", "")):
        return None

    if pm_cfg.get("model_id") and pm_cfg.get("base_url"):
        api_key = pm_cfg.get("api_key") or settings.custom_provider_config.get("api_key", "")
        return ChatOpenAI(
            model=pm_cfg["model_id"],
            api_key=api_key,
            base_url=pm_cfg["base_url"],
            temperature=0.7,
            streaming=True,
        )

    # Fallback: settings existentes
    provider = settings.llm_provider

    if provider == "openai":
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.7,
            streaming=True,
        )
    elif provider == "anthropic":
        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=0.7,
            streaming=True,
        )
    elif provider == "ollama":
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0.7,
        )
    elif provider == "custom_openai":
        cfg = settings.custom_provider_config
        return ChatOpenAI(
            model=cfg["model"],
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            temperature=0.7,
            streaming=True,
        )
    else:
        raise ValueError(
            f"Provider desconhecido: {provider}. "
            f"Use: openai, anthropic, ollama, custom_openai"
        )


async def generate_codex_stream(
    messages: list[BaseMessage],
    model: str = "gpt-4o",
    instructions: str = "",
    response_mode: str = "normal",
    reasoning_effort: str | None = None,
) -> AsyncGenerator[Tuple[str, str], None]:
    """Gera resposta em streaming usando Codex ChatGPT (nova API Responses).
    
    Usa o pool de contas, escolhe a melhor, faz refresh se precisar.
    """
    account = await get_best_account("codex-chatgpt")
    if not account:
        yield ("error", "Nenhuma conta Codex disponível. Adicione uma conta no Provider Manager.")
        return

    access_token = account.get("access_token", "")
    account_id = account.get("account_id", "")
    
    if not access_token or not account_id:
        yield ("error", "Conta Codex inválida (sem tokens).")
        return

    # Extrai system prompt como instructions (se houver)
    system_msg = ""
    user_msgs = []
    for m in messages:
        if isinstance(m, SystemMessage):
            system_msg = str(m.content)
        else:
            user_msgs.append(m)

    # Converte mensagens pro formato Codex (sem o system message)
    codex_messages = _convert_messages_to_codex(user_msgs)
    final_instructions = instructions or system_msg
    mode = normalize_response_mode(response_mode, default=settings.codex_response_mode_default)
    profile = CODEX_MODE_PROFILES[mode]
    selected_effort = normalize_reasoning_effort(reasoning_effort, mode=mode)

    async for typ, text in chat_completion_stream(
        access_token=access_token,
        account_id=account_id,
        model=model,
        messages=codex_messages,
        instructions=final_instructions,
        reasoning_effort=codex_wire_reasoning_effort(selected_effort),
        reasoning_summary=str(profile["reasoning_summary"]),
        typed_sse=settings.codex_sse_enabled,
    ):
        yield (typ, text)


async def generate_stream(
    messages: list[BaseMessage],
    provider_config: dict | None = None,
    response_mode: str = "normal",
    reasoning_effort: str | None = None,
) -> AsyncGenerator[Tuple[str, str], None]:
    """Gera resposta em streaming, emitindo tuplas (tipo, texto).

    Args:
        messages: Lista de mensagens no formato LangChain.

    Yields:
        Tuplas (tipo, texto):
        - ("reasoning", str) → pensamento interno do modelo
        - ("content", str)   → texto final da resposta
        - ("error", str)     → erro (Codex)
    """
    pm_cfg = provider_config or get_active_config()
    
    # ─── Codex ChatGPT ───
    if _is_codex_provider(pm_cfg.get("provider_id", "")):
        model_id = pm_cfg.get("model_id", "gpt-4o")
        async for chunk in generate_codex_stream(
            messages,
            model=model_id,
            response_mode=response_mode,
            reasoning_effort=reasoning_effort,
        ):
            yield chunk
        return

    if _is_opencode_provider(pm_cfg):
        async for chunk in generate_opencode_stream(messages, pm_cfg):
            yield chunk
        return

    # ─── Outros provedores (OpenAI, Anthropic, etc.) ───
    llm = get_llm(provider_config=pm_cfg)
    if llm is None:
        yield ("error", "Nenhum LLM disponível para o provider ativo.")
        return

    async for chunk in llm.astream(messages):
        if isinstance(chunk, AIMessageChunk):
            reasoning = ""
            for key in ("reasoning_content", "reasoning", "thinking"):
                reasoning = _coerce_stream_text(chunk.additional_kwargs.get(key))
                if reasoning:
                    break
            if reasoning:
                for part in _smooth_stream_parts(reasoning):
                    yield ("reasoning", part)
                continue

        if chunk.content:
            content = _coerce_stream_text(chunk.content)
            if not content:
                continue
            parts = _smooth_stream_parts(content)
            for index, part in enumerate(parts):
                yield ("content", part)
                if len(parts) > 1 and index < len(parts) - 1:
                    await asyncio.sleep(0.004)


async def generate(messages: list[BaseMessage], provider_config: dict | None = None) -> str:
    """Gera resposta completa (sem streaming)."""
    full = ""
    async for typ, text in generate_stream(messages, provider_config=provider_config):
        if typ == "content":
            full += text
    return full
