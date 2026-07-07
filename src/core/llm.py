"""Interface unificada para múltiplos provedores de LLM.
Suporta OpenAI, Anthropic, Ollama, Codex ChatGPT e qualquer API compatível com OpenAI.
Gera streaming com separação de reasoning_content e content.
"""

import json
from typing import AsyncGenerator, Tuple, Optional
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessageChunk, HumanMessage, SystemMessage

from src.config import settings
from src.core.provider_manager import get_active_config
from src.core.account_pool import get_best_account, fetch_codex_quota
from src.core.codex_client import chat_completion_stream


def _is_codex_provider(provider_id: str) -> bool:
    return provider_id == "codex-chatgpt"


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
    reasoning_effort: str = "medium",
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

    async for chunk in chat_completion_stream(
        access_token=access_token,
        account_id=account_id,
        model=model,
        messages=codex_messages,
        instructions=final_instructions,
        reasoning_effort=reasoning_effort,
    ):
        if chunk.startswith("ERRO:"):
            yield ("error", chunk)
        else:
            yield ("content", chunk)


async def generate_stream(
    messages: list[BaseMessage],
    provider_config: dict | None = None,
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
            reasoning_effort="high" if "codex" in model_id.lower() else "medium",
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
            reasoning = chunk.additional_kwargs.get("reasoning_content")
            if reasoning:
                yield ("reasoning", reasoning)
                continue

        if chunk.content:
            yield ("content", chunk.content)


async def generate(messages: list[BaseMessage], provider_config: dict | None = None) -> str:
    """Gera resposta completa (sem streaming)."""
    full = ""
    async for typ, text in generate_stream(messages, provider_config=provider_config):
        if typ == "content":
            full += text
    return full
