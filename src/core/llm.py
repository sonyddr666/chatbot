"""Interface unificada para múltiplos provedores de LLM.
Suporta OpenAI, Anthropic, Ollama, Codex ChatGPT e qualquer API compatível com OpenAI.
Gera streaming com separação de reasoning_content e content.
"""

import asyncio
import json
from typing import AsyncGenerator, Tuple, Optional
from urllib.parse import urlparse

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
from src.core.model_capabilities import adapt_reasoning_effort


_REASONING_FIELDS = ("reasoning_content", "reasoning", "thinking", "analysis", "thought")


def _is_codex_provider(provider_id: str) -> bool:
    return provider_id == "codex-chatgpt"


def _is_antigravity_provider(provider_id: str) -> bool:
    return provider_id == "antigravity"


def _is_grok_provider(provider_id: str) -> bool:
    return provider_id == "grok-oauth"


def _is_opencode_provider(config: dict) -> bool:
    provider_id = str(config.get("provider_id", "")).lower()
    base_url = str(config.get("base_url", "")).lower()
    return provider_id.startswith("opencode-") or "opencode.ai/" in base_url


def _is_openai_compatible_provider(config: dict) -> bool:
    api_format = str(config.get("api_format", "chat_completions")).strip().lower()
    return api_format in {
        "chat_completions",
        "custom",
        "openai",
        "openai_compatible",
        "openai_chat_completions",
    }


def _provider_auth_headers(api_key: str, auth_type: str = "") -> dict[str, str]:
    """Build the documented credential header for supported catalog auth schemes."""
    if not api_key:
        return {}
    normalized = str(auth_type or "").strip().lower()
    if normalized in {"x_api_key", "x-api-key"}:
        return {"X-API-Key": api_key}
    if normalized == "authorization_api_key_scheme":
        return {"Authorization": f"Api-Key {api_key}"}
    if normalized == "clarifai_pat":
        return {"Authorization": f"Key {api_key}"}
    return {"Authorization": f"Bearer {api_key}"}


def _coerce_stream_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_coerce_stream_text(item) for item in value)
    if isinstance(value, dict):
        for key in ("text", "content", *_REASONING_FIELDS):
            if key in value:
                return _coerce_stream_text(value[key])
    return ""


def _openai_delta_parts(delta: dict) -> list[tuple[str, str]]:
    """Normalize common reasoning fields used by OpenAI-compatible gateways."""
    parts: list[tuple[str, str]] = []
    structured_reasoning = False
    for key in _REASONING_FIELDS:
        reasoning = _coerce_stream_text(delta.get(key))
        if reasoning:
            parts.append(("reasoning", reasoning))
            structured_reasoning = True
            break
    else:
        reasoning_details = delta.get("reasoning_details")
        if isinstance(reasoning_details, list):
            visible_details = []
            for detail in reasoning_details:
                if not isinstance(detail, dict):
                    continue
                detail_type = str(detail.get("type", ""))
                if detail_type == "reasoning.encrypted":
                    continue
                detail_text = _coerce_stream_text(
                    detail.get("text") or detail.get("summary") or detail.get("content")
                )
                if detail_text:
                    visible_details.append(detail_text)
            if visible_details:
                parts.append(("reasoning", "".join(visible_details)))
                structured_reasoning = True

    content_value = delta.get("content")
    if isinstance(content_value, list):
        reasoning_blocks: list[str] = []
        content_blocks: list[str] = []
        for block in content_value:
            if not isinstance(block, dict):
                text = _coerce_stream_text(block)
                if text:
                    content_blocks.append(text)
                continue
            block_type = str(block.get("type", "")).strip().lower().replace("-", "_")
            is_reasoning_block = (
                block.get("thought") is True
                or block_type in {
                    "analysis",
                    "reasoning",
                    "reasoning_text",
                    "thinking",
                    "thought",
                }
            )
            text = _coerce_stream_text(block)
            if not text:
                continue
            if is_reasoning_block and not structured_reasoning:
                reasoning_blocks.append(text)
            elif not is_reasoning_block:
                content_blocks.append(text)
        if reasoning_blocks:
            parts.append(("reasoning", "".join(reasoning_blocks)))
        if content_blocks:
            parts.append(("content", "".join(content_blocks)))
    else:
        content = _coerce_stream_text(content_value)
        if content:
            parts.append(("content", content))
    return parts


class _InlineReasoningParser:
    """Split common inline reasoning tags without provider-specific rules.

    Some OpenAI-compatible models put reasoning inside the normal ``content``
    field (for example ``<think>...</think>answer``).  The parser is deliberately
    conservative: an opening tag is only special at the start of the response,
    after optional whitespace.  Tags appearing later in prose or code remain
    ordinary content.
    """

    _TAGS = ("think", "thought", "reasoning", "analysis")

    def __init__(self) -> None:
        self._state = "probing"
        self._buffer = ""
        self._tag = ""

    @staticmethod
    def _split_safe_suffix(value: str, marker: str) -> tuple[str, str]:
        """Keep a possible partial closing tag for the next SSE chunk."""
        lowered = value.lower()
        marker = marker.lower()
        max_size = min(len(value), len(marker) - 1)
        for size in range(max_size, 0, -1):
            if lowered.endswith(marker[:size]):
                return value[:-size], value[-size:]
        return value, ""

    def feed(self, text: str) -> list[tuple[str, str]]:
        if not text:
            return []
        if self._state == "content":
            return [("content", text)]

        self._buffer += text
        if self._state == "probing":
            candidate = self._buffer.lstrip()
            if not candidate:
                return []
            lowered = candidate.lower()
            opening_tags = {tag: f"<{tag}>" for tag in self._TAGS}
            for tag, opening in opening_tags.items():
                if lowered.startswith(opening):
                    self._tag = tag
                    self._buffer = candidate[len(opening):]
                    self._state = "reasoning"
                    break
            else:
                if any(opening.startswith(lowered) for opening in opening_tags.values()):
                    return []
                result = self._buffer
                self._buffer = ""
                self._state = "content"
                return [("content", result)]

        closing = f"</{self._tag}>"
        lowered = self._buffer.lower()
        closing_index = lowered.find(closing)
        if closing_index >= 0:
            reasoning = self._buffer[:closing_index]
            content = self._buffer[closing_index + len(closing):]
            self._buffer = ""
            self._state = "content"
            parts: list[tuple[str, str]] = []
            if reasoning:
                parts.append(("reasoning", reasoning))
            if content:
                parts.append(("content", content))
            return parts

        safe, retained = self._split_safe_suffix(self._buffer, closing)
        self._buffer = retained
        return [("reasoning", safe)] if safe else []

    def disable(self) -> list[tuple[str, str]]:
        """Stop inline parsing when the provider supplies structured reasoning."""
        pending = self._buffer
        self._buffer = ""
        self._state = "content"
        return [("content", pending)] if pending else []

    def finish(self) -> list[tuple[str, str]]:
        if not self._buffer:
            return []
        pending = self._buffer
        self._buffer = ""
        if self._state == "reasoning":
            return [("reasoning", pending)]
        return [("content", pending)]


class _OpenAIReasoningNormalizer:
    """Prefer native reasoning fields, then fall back to inline tag parsing."""

    def __init__(self) -> None:
        self._inline = _InlineReasoningParser()
        self._structured_reasoning = False

    def feed(self, typ: str, text: str) -> list[tuple[str, str]]:
        if typ == "reasoning":
            pending = self._inline.disable() if not self._structured_reasoning else []
            self._structured_reasoning = True
            return [*pending, ("reasoning", text)]
        if typ == "content" and not self._structured_reasoning:
            return self._inline.feed(text)
        return [(typ, text)] if text else []

    def finish(self) -> list[tuple[str, str]]:
        if self._structured_reasoning:
            return []
        return self._inline.finish()


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


def _chat_completions_url(provider_config: dict) -> str:
    base_url = str(provider_config.get("base_url", "")).strip().rstrip("/")
    endpoint = str(provider_config.get("endpoint", "")).strip()
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    if endpoint:
        return base_url + "/" + endpoint.lstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    is_ollama = str(provider_config.get("provider_id", "")).lower() == "ollama"
    if is_ollama and not base_url.endswith("/v1"):
        base_url += "/v1"
    return base_url + "/chat/completions"


def _provider_reasoning_style(provider_config: dict) -> str:
    explicit = str(provider_config.get("reasoning_style", "")).strip().lower()
    if explicit in {"object", "reasoning", "reasoning_object", "morph", "openrouter"}:
        return "reasoning_object"
    if explicit in {"effort", "reasoning_effort", "openai"}:
        return "reasoning_effort"
    if explicit in {"none", "disabled", "off"}:
        return "none"

    provider_id = str(provider_config.get("provider_id", "")).lower()
    hostname = urlparse(str(provider_config.get("base_url", ""))).hostname or ""
    if "morphllm.com" in hostname or "openrouter.ai" in hostname:
        return "reasoning_object"
    if hostname == "api.openai.com" or provider_id == "openai":
        return "reasoning_effort"
    if (
        provider_id.startswith("opencode-")
        or "opencode.ai" in hostname
        or provider_id == "ollama"
        or "localhost" in hostname
    ):
        return "none"
    return "adaptive"


def _openai_request_variants(
    messages: list[BaseMessage],
    provider_config: dict,
    response_mode: str,
    reasoning_effort: str | None,
) -> list[dict]:
    mode = normalize_response_mode(response_mode, default=settings.codex_response_mode_default)
    requested_effort = normalize_reasoning_effort(reasoning_effort, mode=mode)
    effort = adapt_reasoning_effort(provider_config, requested_effort)
    base_payload = {
        "model": str(provider_config.get("model_id", "")).strip(),
        "messages": _messages_for_openai(messages),
        "stream": True,
    }
    if provider_config.get("supports_temperature") is not False:
        base_payload["temperature"] = 0.7
    style = _provider_reasoning_style(provider_config)
    extras: list[dict]
    if not effort:
        extras = [{}]
    elif style == "reasoning_object":
        extras = [{"reasoning": {"effort": effort}}, {}]
    elif style == "reasoning_effort":
        extra = {"reasoning_effort": effort}
        hostname = (urlparse(str(provider_config.get("base_url", ""))).hostname or "").lower()
        if hostname == "api.groq.com" and effort != "none":
            extra["reasoning_format"] = "parsed"
        extras = [extra, {}]
    else:
        extras = [{}]

    variants: list[dict] = []
    for extra in extras:
        payload = {**base_payload, **extra}
        if payload not in variants:
            variants.append(payload)
    return variants


def _can_retry_without_reasoning(status_code: int, detail: str) -> bool:
    if status_code not in {400, 404, 422}:
        return False
    lowered = detail.lower()
    if "reasoning" not in lowered:
        return False
    return any(
        marker in lowered
        for marker in (
            "unknown",
            "unsupported",
            "not support",
            "not allowed",
            "unrecognized",
            "unexpected",
            "extra_forbidden",
            "additional propert",
            "invalid parameter",
            "invalid field",
            "invalid value",
            "expected one of",
            "must be one of",
        )
    )


async def _iter_openai_payloads(response: httpx.Response) -> AsyncGenerator[str, None]:
    """Yield complete SSE data payloads, with a JSON-response fallback."""
    data_lines: list[str] = []
    raw_lines: list[str] = []
    saw_sse_data = False
    async for line in response.aiter_lines():
        if line == "":
            if data_lines:
                saw_sse_data = True
                yield "\n".join(data_lines)
                data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            if data_lines:
                candidate = "\n".join(data_lines)
                try:
                    json.loads(candidate)
                except json.JSONDecodeError:
                    pass
                else:
                    saw_sse_data = True
                    yield candidate
                    data_lines = []
            data_lines.append(line[5:].lstrip(" "))
            continue
        raw_lines.append(line)

    if data_lines:
        saw_sse_data = True
        yield "\n".join(data_lines)
    if not saw_sse_data and raw_lines:
        yield "\n".join(raw_lines)


def _openai_event_parts(event: dict) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    for choice in event.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta") or choice.get("message") or {}
        if isinstance(delta, dict):
            parts.extend(_openai_delta_parts(delta))
    return parts


def _provider_error(provider_config: dict, message: str) -> RuntimeError:
    label = str(
        provider_config.get("name")
        or provider_config.get("provider_id")
        or "Provider OpenAI-compatible"
    )
    return RuntimeError(f"{label}: {message}")


async def resolve_provider_config(provider_config: dict) -> dict:
    """Resolve provider-specific configuration before any outbound model request."""
    base_url = str(provider_config.get("base_url") or "").strip()
    lowered = base_url.lower()
    if not any(marker in lowered for marker in ("coloque_seu_account_id", "{account_id}", "<account_id>")):
        return provider_config

    api_key = str(provider_config.get("api_key") or "").strip()
    if not api_key:
        raise _provider_error(provider_config, "API Token da Cloudflare nao configurado")

    from src.core.cloudflare_provider import discover_cloudflare_accounts, workers_ai_base_url

    try:
        accounts = await discover_cloudflare_accounts(api_key)
    except (ValueError, RuntimeError) as exc:
        raise _provider_error(provider_config, str(exc)) from exc
    if not accounts:
        raise _provider_error(
            provider_config,
            "o token nao conseguiu listar nenhuma conta. Abra Providers > Cloudflare Workers AI > API Key "
            "e informe o Account ID manualmente, ou use um token com Account Settings: Read.",
        )
    if len(accounts) > 1:
        raise _provider_error(
            provider_config,
            f"o token acessa {len(accounts)} contas. Abra Providers > Cloudflare Workers AI > API Key "
            "e escolha a conta correta.",
        )

    resolved_url = workers_ai_base_url(accounts[0]["id"])
    resolved = {**provider_config, "base_url": resolved_url}
    provider_id = str(provider_config.get("provider_id") or "")
    if provider_id:
        from src.core.provider_manager import update_provider
        await asyncio.to_thread(update_provider, provider_id, {"base_url": resolved_url})
    return resolved


async def generate_openai_compatible_stream(
    messages: list[BaseMessage],
    provider_config: dict,
    response_mode: str = "normal",
    reasoning_effort: str | None = None,
) -> AsyncGenerator[Tuple[str, str], None]:
    """Stream any Chat Completions-compatible provider without losing reasoning fields."""
    provider_config = await resolve_provider_config(provider_config)
    base_url = str(provider_config.get("base_url", "")).strip()
    model = str(provider_config.get("model_id", "")).strip()
    api_key = str(provider_config.get("api_key", "")).strip()
    if not base_url or not model:
        raise _provider_error(provider_config, "URL ou modelo ausente")
    endpoint = _chat_completions_url(provider_config)
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
    }
    headers.update(_provider_auth_headers(api_key, str(provider_config.get("auth_type") or "")))

    variants = _openai_request_variants(
        messages,
        provider_config,
        response_mode,
        reasoning_effort,
    )
    timeout = httpx.Timeout(120.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for attempt, payload in enumerate(variants):
            async with client.stream(
                "POST",
                endpoint,
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    detail = (await response.aread()).decode("utf-8", errors="replace")[:1000]
                    has_fallback = attempt < len(variants) - 1
                    if has_fallback and _can_retry_without_reasoning(response.status_code, detail):
                        continue
                    raise _provider_error(
                        provider_config,
                        f"HTTP {response.status_code}: {detail}",
                    )

                received_text = False
                received_content = False
                pending_type = ""
                pending_text = ""
                reasoning_normalizer = _OpenAIReasoningNormalizer()
                async for raw in _iter_openai_payloads(response):
                    raw = raw.strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    if event.get("error"):
                        raise _provider_error(provider_config, f"erro no stream: {event['error']}")
                    normalized_parts: list[tuple[str, str]] = []
                    for typ, text in _openai_event_parts(event):
                        normalized_parts.extend(reasoning_normalizer.feed(typ, text))
                    for typ, text in normalized_parts:
                        received_text = True
                        if typ == "content":
                            received_content = True
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

                for typ, text in reasoning_normalizer.finish():
                    received_text = True
                    if typ == "content":
                        received_content = True
                    if pending_type and pending_type != typ and pending_text:
                        for piece in _smooth_stream_parts(pending_text):
                            yield (pending_type, piece)
                        pending_text = ""
                    pending_type = typ
                    pending_text += text

                if pending_type and pending_text:
                    for piece in _smooth_stream_parts(pending_text):
                        yield (pending_type, piece)
                if not received_text:
                    raise _provider_error(provider_config, "stream encerrado sem conteúdo")
                if not received_content:
                    raise _provider_error(
                        provider_config,
                        "o provider enviou raciocinio, mas encerrou o stream sem resposta final",
                    )
                return


async def generate_opencode_stream(
    messages: list[BaseMessage],
    provider_config: dict,
    response_mode: str = "normal",
    reasoning_effort: str | None = None,
) -> AsyncGenerator[Tuple[str, str], None]:
    """Backward-compatible OpenCode entrypoint using the shared adapter."""
    async for chunk in generate_openai_compatible_stream(
        messages,
        provider_config,
        response_mode=response_mode,
        reasoning_effort=reasoning_effort,
    ):
        yield chunk


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
            codex_parts = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text" and part.get("text"):
                    codex_parts.append({"type": "input_text", "text": str(part["text"])})
                elif part.get("type") == "image_url":
                    image_value = part.get("image_url")
                    image_url = image_value.get("url") if isinstance(image_value, dict) else image_value
                    if image_url:
                        codex_parts.append({"type": "input_image", "image_url": str(image_url)})
            content = codex_parts or [{"type": "input_text", "text": ""}]

        result.append({"role": role, "content": content if isinstance(content, list) else str(content)})
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
        common_kwargs = {
            "model": pm_cfg["model_id"],
            "api_key": api_key,
            "base_url": pm_cfg["base_url"],
            "streaming": True,
        }
        if pm_cfg.get("supports_temperature") is not False:
            common_kwargs["temperature"] = 0.7
        if str(pm_cfg.get("api_format") or "").lower() == "anthropic_messages":
            return ChatAnthropic(**common_kwargs)
        return ChatOpenAI(**common_kwargs)

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

    if _is_antigravity_provider(pm_cfg.get("provider_id", "")):
        from src.core.antigravity_client import chat_stream as antigravity_chat_stream

        user_id = int(pm_cfg.get("user_id") or 0)
        if not user_id:
            yield ("error", "Antigravity exige uma sessao de usuario autenticada.")
            return
        async for chunk in antigravity_chat_stream(
            user_id,
            messages,
            model=str(pm_cfg.get("model_id") or "auto"),
            reasoning_effort=str(reasoning_effort or "low"),
        ):
            yield chunk
        return

    if _is_grok_provider(pm_cfg.get("provider_id", "")):
        from src.core.grok_client import chat_stream as grok_chat_stream

        user_id = int(pm_cfg.get("user_id") or 0)
        if not user_id:
            yield ("error", "Grok OAuth exige uma sessao de usuario autenticada.")
            return
        async for chunk in grok_chat_stream(
            user_id,
            messages,
            model=str(pm_cfg.get("model_id") or "grok-4.5"),
            reasoning_effort=reasoning_effort,
        ):
            yield chunk
        return
    
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
        async for chunk in generate_opencode_stream(
            messages,
            pm_cfg,
            response_mode=response_mode,
            reasoning_effort=reasoning_effort,
        ):
            yield chunk
        return

    if _is_openai_compatible_provider(pm_cfg) and pm_cfg.get("base_url"):
        async for chunk in generate_openai_compatible_stream(
            messages,
            pm_cfg,
            response_mode=response_mode,
            reasoning_effort=reasoning_effort,
        ):
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
            for key in _REASONING_FIELDS:
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
