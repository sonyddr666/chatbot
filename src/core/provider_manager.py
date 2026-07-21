"""Gerenciador de provedores (providers) de IA.
Armazena provedores customizados em JSON e mescla com os built-in do config.py.
"""

import json
import os
import shutil
from copy import deepcopy
from typing import Optional
from datetime import datetime, timezone
from src.config import settings

DATA_DIR = "./data"
PROVIDERS_FILE = os.path.join(DATA_DIR, "providers.json")

# ─── Estrutura de dados ─────────────────────────────────────────────

DEFAULT_PROVIDERS_DATA = {
    "custom_providers": [],
    "active_provider_id": "opencode-zen-free",
    "active_model_id": "deepseek-v4-flash-free",
    "provider_keys": {},  # chaves salvas via UI (built-in ou custom)
    "builtin_provider_overrides": {},  # provider_id -> { enabled }
    "builtin_model_overrides": {},  # provider_id -> model_id -> { enabled/name/context_length }
    "builtin_dynamic_models": {},  # provider_id -> models discovered from provider APIs
}

# ─── Helpers ─────────────────────────────────────────────────────────

def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_raw() -> dict:
    _ensure_dir()
    if not os.path.exists(PROVIDERS_FILE):
        _save_raw(DEFAULT_PROVIDERS_DATA)
        return dict(DEFAULT_PROVIDERS_DATA)
    try:
        with open(PROVIDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return dict(DEFAULT_PROVIDERS_DATA)


def _save_raw(data: dict):
    _ensure_dir()
    with open(PROVIDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ─── API pública ────────────────────────────────────────────────────

BUILTIN_PROVIDERS = {
    # ╔══════════════════════════════════════════════════════════════╗
    # ║  OPENCODE GO — Assinatura de Baixo Custo                   ║
    # ║  https://opencode.ai/zen/go/v1                              ║
    # ║  Modelos econômicos / open-source via gateway               ║
    # ╚══════════════════════════════════════════════════════════════╝
    "opencode-go": {
        "name": "OpenCode Go",
        "description": "Assinatura de baixo custo",
        "base_url": "https://opencode.ai/zen/go/v1",
        "api_format": "chat_completions",
        "provider_type": "builtin",
        "enabled": True,
        "models": [
            # DeepSeek
            {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "context_length": 1000000, "enabled": True},
            {"id": "deepseek-v4-pro",   "name": "DeepSeek V4 Pro",   "context_length": 1000000, "enabled": False},
            # GLM (Zhipu)
            {"id": "glm-5.2",           "name": "GLM 5.2",           "context_length": 1000000, "enabled": False},
            {"id": "glm-5.1",           "name": "GLM 5.1",           "context_length": 200000, "enabled": False},
            # Kimi (Moonshot)
            {"id": "kimi-k2.7-code",    "name": "Kimi K2.7 Code",    "context_length": 262000, "enabled": False},
            {"id": "kimi-k2.6",         "name": "Kimi K2.6",         "context_length": 262000, "enabled": False},
            # MiMo
            {"id": "mimo-v2.5",         "name": "MiMo V2.5",         "context_length": 1000000, "enabled": False},
            {"id": "mimo-v2.5-pro",     "name": "MiMo V2.5 Pro",     "context_length": 1000000, "enabled": False},
            # MiniMax
            {"id": "minimax-m3",        "name": "MiniMax M3",        "context_length": 1000000, "enabled": False},
            {"id": "minimax-m2.7",      "name": "MiniMax M2.7",      "context_length": 205000, "enabled": False},
            # Qwen
            {"id": "qwen3.7-max",       "name": "Qwen 3.7 Max",       "context_length": 1000000, "enabled": False},
            {"id": "qwen3.7-plus",      "name": "Qwen 3.7 Plus",      "context_length": 1000000, "enabled": False},
            {"id": "qwen3.6-plus",      "name": "Qwen 3.6 Plus",      "context_length": 1000000, "enabled": False},
        ],
    },

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  OPENCODE ZEN — Gateway Premium Pay-as-you-go               ║
    # ║  https://opencode.ai/zen/v1                                 ║
    # ╚══════════════════════════════════════════════════════════════╝
    "opencode-zen": {
        "name": "OpenCode Zen",
        "description": "Gateway pay-as-you-go",
        "base_url": "https://opencode.ai/zen/v1",
        "api_format": "chat_completions",
        "provider_type": "builtin",
        "enabled": True,
        "models": [
            # ─── OpenAI ───
            {"id": "gpt-5.5",             "name": "GPT-5.5",              "context_length": 128000, "enabled": True},
            {"id": "gpt-5.5-pro",         "name": "GPT-5.5 Pro",          "context_length": 400000, "enabled": False},
            {"id": "gpt-5.4",             "name": "GPT-5.4",              "context_length": 1050000, "enabled": True},
            {"id": "gpt-5.4-pro",         "name": "GPT-5.4 Pro",          "context_length": 1050000, "enabled": False},
            {"id": "gpt-5.4-mini",        "name": "GPT-5.4 Mini",         "context_length": 1050000, "enabled": True},
            {"id": "gpt-5.4-nano",        "name": "GPT-5.4 Nano",         "context_length": 1050000, "enabled": False},
            {"id": "gpt-5.3-codex",       "name": "GPT-5.3 Codex",        "context_length": 400000, "enabled": False},
            {"id": "gpt-5.3-codex-spark", "name": "GPT-5.3 Codex Spark",  "context_length": 400000, "enabled": False},
            {"id": "gpt-5.2",             "name": "GPT-5.2",              "context_length": 400000, "enabled": False},
            {"id": "gpt-5.2-codex",       "name": "GPT-5.2 Codex",        "context_length": 400000, "enabled": False, "deprecated": True},
            {"id": "gpt-5.1",             "name": "GPT-5.1",              "context_length": 400000, "enabled": False},
            {"id": "gpt-5.1-codex",       "name": "GPT-5.1 Codex",        "context_length": 400000, "enabled": False, "deprecated": True},
            {"id": "gpt-5.1-codex-max",   "name": "GPT-5.1 Codex Max",    "context_length": 400000, "enabled": False, "deprecated": True},
            {"id": "gpt-5.1-codex-mini",  "name": "GPT-5.1 Codex Mini",   "context_length": 400000, "enabled": False, "deprecated": True},
            {"id": "gpt-5",               "name": "GPT-5",               "context_length": 400000, "enabled": False},
            {"id": "gpt-5-codex",         "name": "GPT-5 Codex",          "context_length": 400000, "enabled": False, "deprecated": True},
            {"id": "gpt-5-nano",          "name": "GPT-5 Nano",           "context_length": 400000, "enabled": False},
            # ─── Anthropic Claude ───
            {"id": "claude-fable-5",       "name": "Claude Fable 5",       "context_length": 1000000, "enabled": False},
            {"id": "claude-opus-4-8",      "name": "Claude Opus 4.8",      "context_length": 200000, "enabled": False},
            {"id": "claude-opus-4-7",      "name": "Claude Opus 4.7",      "context_length": 200000, "enabled": False},
            {"id": "claude-opus-4-6",      "name": "Claude Opus 4.6",      "context_length": 200000, "enabled": False},
            {"id": "claude-opus-4-5",      "name": "Claude Opus 4.5",      "context_length": 200000, "enabled": False},
            {"id": "claude-sonnet-5",      "name": "Claude Sonnet 5",      "context_length": 200000, "enabled": True},
            {"id": "claude-sonnet-4-6",    "name": "Claude Sonnet 4.6",    "context_length": 200000, "enabled": True},
            {"id": "claude-sonnet-4-5",    "name": "Claude Sonnet 4.5",    "context_length": 200000, "enabled": False},
            {"id": "claude-haiku-4-5",     "name": "Claude Haiku 4.5",     "context_length": 200000, "enabled": False},
            # ─── Google Gemini ───
            {"id": "gemini-3.5-flash",     "name": "Gemini 3.5 Flash",     "context_length": 1000000, "enabled": False},
            {"id": "gemini-3.1-pro",      "name": "Gemini 3.1 Pro",       "context_length": 1000000, "enabled": False},
            {"id": "gemini-3-flash",      "name": "Gemini 3 Flash",       "context_length": 1000000, "enabled": False},
            # ─── Qwen ───
            {"id": "qwen3.7-max",         "name": "Qwen 3.7 Max",         "context_length": 1000000, "enabled": False},
            {"id": "qwen3.7-plus",        "name": "Qwen 3.7 Plus",        "context_length": 1000000, "enabled": False},
            {"id": "qwen3.6-plus",        "name": "Qwen 3.6 Plus",        "context_length": 1000000, "enabled": False},
            {"id": "qwen3.5-plus",        "name": "Qwen 3.5 Plus",        "context_length": 1000000, "enabled": False},
            # ─── DeepSeek ───
            {"id": "deepseek-v4-pro",      "name": "DeepSeek V4 Pro",      "context_length": 1000000, "enabled": False},
            {"id": "deepseek-v4-flash",    "name": "DeepSeek V4 Flash",    "context_length": 1000000, "enabled": True},
            # ─── MiniMax ───
            {"id": "minimax-m3",          "name": "MiniMax M3",           "context_length": 1000000, "enabled": False},
            {"id": "minimax-m2.7",        "name": "MiniMax M2.7",         "context_length": 205000, "enabled": False},
            {"id": "minimax-m2.5",        "name": "MiniMax M2.5",         "context_length": 205000, "enabled": False, "deprecated": True},
            # ─── GLM ───
            {"id": "glm-5.2",             "name": "GLM 5.2",              "context_length": 1000000, "enabled": False},
            {"id": "glm-5.1",             "name": "GLM 5.1",              "context_length": 200000, "enabled": False},
            {"id": "glm-5",               "name": "GLM 5",                "context_length": 200000, "enabled": False, "deprecated": True},
            # ─── Kimi ───
            {"id": "kimi-k2.7-code",      "name": "Kimi K2.7 Code",       "context_length": 262000, "enabled": False},
            {"id": "kimi-k2.6",           "name": "Kimi K2.6",            "context_length": 262000, "enabled": False},
            {"id": "kimi-k2.5",           "name": "Kimi K2.5",            "context_length": 262000, "enabled": False, "deprecated": True},
            # ─── Grok ───
            {"id": "grok-build-0.1",      "name": "Grok Build 0.1",       "context_length": 128000, "enabled": False},
        ],
    },

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  OPENCODE ZEN FREE — Modelos Gratuitos                      ║
    # ║  https://opencode.ai/zen/v1                                 ║
    # ╚══════════════════════════════════════════════════════════════╝
    "opencode-zen-free": {
        "name": "OpenCode Zen Free",
        "description": "Modelos gratuitos",
        "base_url": "https://opencode.ai/zen/v1",
        "api_format": "chat_completions",
        "provider_type": "builtin",
        "enabled": True,
        "models": [
            {"id": "deepseek-v4-flash-free", "name": "DeepSeek V4 Flash Free", "context_length": 1000000, "enabled": True},
            {"id": "mimo-v2.5-free",        "name": "MiMo V2.5 Free",        "context_length": 1000000, "enabled": False},
            {"id": "north-mini-code-free",   "name": "North Mini Code Free",  "context_length": 200000, "enabled": True},
            {"id": "nemotron-3-ultra-free",  "name": "Nemotron 3 Ultra Free", "context_length": 200000, "enabled": False},
            {"id": "big-pickle",             "name": "Big Pickle",            "context_length": 200000, "enabled": False},
        ],
    },

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  OPENAI — API Oficial                                       ║
    # ║  https://api.openai.com/v1                                  ║
    # ╚══════════════════════════════════════════════════════════════╝
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "api_format": "chat_completions",
        "provider_type": "builtin",
        "enabled": True,
        "models": [
            {"id": "gpt-5.4",           "name": "GPT-5.4",        "context_length": 1050000, "enabled": True},
            {"id": "gpt-5.4-pro",       "name": "GPT-5.4 Pro",    "context_length": 1050000, "enabled": False},
            {"id": "gpt-4.1",           "name": "GPT-4.1",        "context_length": 1000000, "enabled": False},
            {"id": "gpt-4.1-mini",      "name": "GPT-4.1 Mini",   "context_length": 1000000, "enabled": True},
            {"id": "gpt-4.1-nano",      "name": "GPT-4.1 Nano",   "context_length": 1000000, "enabled": False},
            {"id": "chatgpt-4o-latest", "name": "GPT-4o (Legacy)","context_length": 128000,  "enabled": True},
        ],
    },

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  ANTHROPIC — API Oficial                                   ║
    # ║  https://api.anthropic.com/v1                               ║
    # ╚══════════════════════════════════════════════════════════════╝
    "anthropic": {
        "name": "Anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "api_format": "anthropic_messages",
        "provider_type": "builtin",
        "enabled": True,
        "models": [
            {"id": "claude-haiku-4-5",   "name": "Claude Haiku 4.5",  "context_length": 200000, "enabled": True},
            {"id": "claude-sonnet-4-6",  "name": "Claude Sonnet 4.6", "context_length": 200000, "enabled": True},
            {"id": "claude-opus-4-8",    "name": "Claude Opus 4.8",   "context_length": 200000, "enabled": False},
            {"id": "claude-fable-5",     "name": "Claude Fable 5",    "context_length": 1000000, "enabled": False},
        ],
    },

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  OLLAMA (Local) — OpenAI Compatible                         ║
    # ║  http://localhost:11434                                     ║
    # ╚══════════════════════════════════════════════════════════════╝
    "ollama": {
        "name": "Ollama (Local)",
        "base_url": "http://localhost:11434",
        "api_format": "openai",
        "provider_type": "builtin",
        "enabled": True,
        "models": [
            {"id": "llama3.1:8b", "name": "Llama 3.1 8B", "context_length": 128000, "enabled": True},
            {"id": "mistral:7b",  "name": "Mistral 7B",  "context_length": 32000,  "enabled": True},
        ],
    },

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  CODEX CHATGPT — Pool de Contas ChatGPT                     ║
    # ║  API: https://chatgpt.com/backend-api                       ║
    # ║  Auth: tokens OAuth (Device Code)                           ║
    # ╚══════════════════════════════════════════════════════════════╝
    "codex-chatgpt": {
        "name": "Codex ChatGPT",
        "description": "Contas ChatGPT via pool de tokens",
        "base_url": "https://chatgpt.com/backend-api",
        "endpoint": "/codex/responses",
        "api_format": "codex",
        "provider_type": "builtin",
        "enabled": True,
        "models": [
            {"id": "gpt-5.6-sol",         "name": "GPT-5.6 Sol (Codex)",          "alias": "gpt-5.6", "usage": "melhor para codigo pesado, raciocinio e tarefas dificeis", "status": "oficial", "context_length": 1050000, "enabled": True},
            {"id": "gpt-5.6-terra",       "name": "GPT-5.6 Terra (Codex)",        "usage": "equilibrio entre inteligencia e custo", "status": "oficial", "context_length": 1050000, "enabled": True},
            {"id": "gpt-5.6-luna",        "name": "GPT-5.6 Luna (Codex)",         "usage": "mais barato e leve para alto volume", "status": "oficial", "context_length": 1050000, "enabled": True},
            {"id": "gpt-5.5",             "name": "GPT-5.5 (Codex)",              "usage": "modelo atual compativel se a conta ou Codex liberar", "status": "confirmar no provider", "context_length": 128000, "enabled": True},
            {"id": "gpt-5.4",             "name": "GPT-5.4 (Codex)",              "usage": "possivel modelo legado ou custom", "status": "nao confirmado na lista publica atual", "context_length": 1050000, "enabled": True},
            {"id": "gpt-5.4-mini",        "name": "GPT-5.4 Mini (Codex)",         "usage": "possivel modelo leve, legado ou custom", "status": "nao confirmado na lista publica atual", "context_length": 1050000, "enabled": True},
            {"id": "gpt-5.3-codex-spark", "name": "GPT-5.3 Codex Spark (Codex)",  "usage": "possivel modelo especifico de Codex ou proxy", "status": "nao confirmado na lista publica atual", "context_length": 400000, "enabled": True},
        ],
    },

    "antigravity": {
        "name": "Antigravity",
        "description": "Google Antigravity via OAuth, com chat multimodal e geracao de imagens",
        "base_url": "https://cloudcode-pa.googleapis.com",
        "endpoint": "/v1internal:streamGenerateContent",
        "api_format": "antigravity",
        "provider_type": "builtin",
        "enabled": settings.antigravity_enabled,
        "models": [
            {
                "id": "auto",
                "name": "Automatico (sincronize a conta)",
                "context_length": 1000000,
                "enabled": True,
            },
        ],
    },

    "grok-oauth": {
        "name": "Grok OAuth",
        "description": "Conta xAI/Grok conectada por OAuth Device Code",
        "base_url": "https://cli-chat-proxy.grok.com/v1",
        "endpoint": "/responses",
        "api_format": "openai_responses",
        "provider_type": "builtin",
        "enabled": True,
        "models": [
            {"id": "grok-4.5", "name": "Grok 4.5", "context_length": 500000, "enabled": True, "supports_images": True, "supports_thinking": True, "supports_tools": True},
            {"id": "grok-build-0.1", "name": "Grok Build 0.1", "context_length": 256000, "enabled": True, "supports_images": True, "supports_thinking": True, "supports_tools": True},
            {"id": "grok-4.3", "name": "Grok 4.3", "context_length": 1000000, "enabled": True, "supports_images": True, "supports_thinking": True, "supports_tools": True},
            {"id": "grok-4.20-0309-reasoning", "name": "Grok 4.20 (Reasoning)", "context_length": 1000000, "enabled": False, "supports_images": True, "supports_thinking": True, "supports_tools": True},
            {"id": "grok-4.20-0309-non-reasoning", "name": "Grok 4.20 (Non-Reasoning)", "context_length": 1000000, "enabled": False, "supports_images": True, "supports_tools": True},
        ],
    },
}


# ─── API Keys para qualquer provider ────────────────────────────────

def get_stored_api_key(provider_id: str) -> str:
    """Retorna a chave salva para qualquer provider (built-in ou custom)."""
    data = _load_raw()
    return data.get("provider_keys", {}).get(provider_id, "")


def set_stored_api_key(provider_id: str, api_key: str) -> bool:
    """Salva a chave de API para qualquer provider."""
    data = _load_raw()
    if "provider_keys" not in data:
        data["provider_keys"] = {}
    if api_key:
        data["provider_keys"][provider_id] = api_key
    else:
        data["provider_keys"].pop(provider_id, None)
    _save_raw(data)
    return True


# Mapeamento de provider_id → nome do atributo em settings
# (porque o ID do provider nem sempre bate com o nome da env var)
PROVIDER_ENV_MAP = {
    "opencode-zen": "opencode_zen_api_key",
    "opencode-zen-free": "opencode_zen_api_key",
    "opencode-zen-openai": "opencode_zen_api_key",
    "opencode-zen-anthropic": "opencode_zen_api_key",
    "opencode-zen-paid": "opencode_zen_api_key",
    "opencode-go": "opencode_go_api_key",
    "opencode-go-anthropic": "opencode_go_api_key",
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "ollama": "",  # Ollama não precisa de chave
}


# Integracoes mantidas pelo produto. Providers antigos salvos como custom continuam
# usando seus modelos e chaves atuais, mas passam a ter semantica built-in na UI.
PROMOTED_BUILTIN_PROVIDER_IDS = frozenset({
    "morph",
    "openrouter",
    "cloudflare-workers-ai",
    "groq",
    "cohere",
    "cerebras",
    "nvidia-nim",
    "google-ai",
})

PROVIDER_RESOURCES = {
    "opencode-go": {"api_key_url": "https://opencode.ai/auth", "docs_url": "https://opencode.ai/docs/zen/"},
    "opencode-zen": {"api_key_url": "https://opencode.ai/auth", "docs_url": "https://opencode.ai/docs/zen/"},
    "opencode-zen-free": {"api_key_url": "https://opencode.ai/auth", "docs_url": "https://opencode.ai/docs/zen/"},
    "openai": {"api_key_url": "https://platform.openai.com/api-keys", "docs_url": "https://platform.openai.com/docs/quickstart"},
    "anthropic": {"api_key_url": "https://console.anthropic.com/settings/keys", "docs_url": "https://docs.anthropic.com/"},
    "ollama": {"api_key_url": "", "docs_url": "https://docs.ollama.com/"},
    "codex-chatgpt": {"api_key_url": "", "docs_url": "https://developers.openai.com/codex/"},
    "antigravity": {"api_key_url": "", "docs_url": "https://antigravity.google/"},
    "grok-oauth": {"api_key_url": "", "docs_url": "https://docs.x.ai/"},
    "morph": {"api_key_url": "https://morphllm.com/dashboard/api-keys", "docs_url": "https://docs.morphllm.com/quickstart"},
    "openrouter": {"api_key_url": "https://openrouter.ai/settings/keys", "docs_url": "https://openrouter.ai/docs/api/reference/authentication"},
    "cloudflare-workers-ai": {"api_key_url": "https://dash.cloudflare.com/profile/api-tokens", "docs_url": "https://developers.cloudflare.com/workers-ai/get-started/rest-api/"},
    "groq": {"api_key_url": "https://console.groq.com/keys", "docs_url": "https://console.groq.com/docs/quickstart"},
    "cohere": {"api_key_url": "https://dashboard.cohere.com/api-keys", "docs_url": "https://docs.cohere.com/reference/about"},
    "cerebras": {"api_key_url": "https://cloud.cerebras.ai/", "docs_url": "https://inference-docs.cerebras.ai/api-reference/authentication"},
    "nvidia-nim": {"api_key_url": "https://build.nvidia.com/settings/api-keys", "docs_url": "https://docs.nvidia.com/nim/"},
    "google-ai": {"api_key_url": "https://aistudio.google.com/apikey", "docs_url": "https://ai.google.dev/gemini-api/docs/api-key"},
}


def _codex_has_accounts() -> bool:
    """Codex não usa API key; usa OAuth account pool."""
    try:
        from src.core.account_pool import list_accounts
        return len(list_accounts("codex-chatgpt")) > 0
    except Exception:
        return False


def _antigravity_has_accounts() -> bool:
    """Global provider data must never reveal another user's OAuth state."""
    return False


def _get_key_source(provider_id: str, current_key: str = "") -> str:
    """Identifica de onde veio a chave de um provider."""
    if not current_key:
        return "none"
    if get_stored_api_key(provider_id):
        return "ui"
    env_attr = PROVIDER_ENV_MAP.get(provider_id, "")
    if env_attr and hasattr(settings, env_attr) and getattr(settings, env_attr, ""):
        return "env"
    # Fallback: só se for o provider ativo
    try:
        active_profile = settings.custom_profile
        if active_profile == provider_id:
            cfg = settings.custom_provider_config
            if cfg.get("api_key"):
                return "fallback"
    except Exception:
        pass
    data = _load_raw()
    for cp in data.get("custom_providers", []):
        if cp["id"] == provider_id and cp.get("api_key", ""):
            return "custom_provider"
    return "unknown"


def get_provider_api_key(provider_id: str) -> str:
    """
    Retorna a melhor chave disponível para um provider.
    Ordem de precedência:
    1. Chave salva via UI (provider_keys em providers.json)
    2. Chave do .env via mapeamento explícito (PROVIDER_ENV_MAP)
    3. Chave do custom_provider_config (perfil ativo do settings)
    4. Chave salva em custom provider no data
    """
    # 1. Chave salva via UI
    stored = get_stored_api_key(provider_id)
    if stored:
        return stored

    # 2. Chave do .env via mapeamento explícito
    env_attr = PROVIDER_ENV_MAP.get(provider_id, "")
    if env_attr and hasattr(settings, env_attr):
        val = getattr(settings, env_attr, "")
        if val:
            return val

    # 3. custom_provider_config (perfil ativo do settings) — só retorna se for o mesmo provider
    # para não vazar chave de um provider para outro
    if provider_id in PROVIDER_ENV_MAP:
        # Só usa fallback se o provider_id é o ativo
        try:
            active_profile = settings.custom_profile
            if active_profile == provider_id:
                cfg = settings.custom_provider_config
                if cfg.get("api_key"):
                    return cfg["api_key"]
        except Exception:
            pass

    # 4. Chave de custom provider
    data = _load_raw()
    for cp in data.get("custom_providers", []):
        if cp["id"] == provider_id:
            return cp.get("api_key", "")

    return ""


def get_provider_status(provider_id: str = "") -> dict:
    """
    Status detalhado de um provider: se tem chave, de onde veio, etc.
    Se provider_id for vazio, usa o provider ativo.
    """
    if not provider_id:
        raw = _load_raw()
        provider_id = raw.get("active_provider_id", "opencode-zen-free")

    provider = get_provider(provider_id, include_keys=True)
    if not provider:
        return {"provider_id": provider_id, "configured": False, "error": "Provider não encontrado"}
    if not provider.get("enabled", True):
        return {"provider_id": provider_id, "configured": False, "error": "Provider desativado"}

    # Codex ChatGPT não usa API key; usa pool OAuth
    if provider_id == "codex-chatgpt":
        has_accounts = _codex_has_accounts()
        return {
            "provider_id": provider_id,
            "provider_name": provider.get("name", provider_id),
            "model_id": provider.get("active_model_id", ""),
            "has_key": has_accounts,
            "key_masked": "oauth-account" if has_accounts else "",
            "key_source": "oauth_pool" if has_accounts else "none",
            "configured": has_accounts,
        }

    # Descobre a fonte da chave
    key = provider.get("api_key", "")
    masked = key[:15] + "..." + key[-4:] if len(key) > 20 else (key[:8] + "..." if key else "")

    stored_ui = get_stored_api_key(provider_id)
    env_attr = PROVIDER_ENV_MAP.get(provider_id, "")
    has_env = bool(env_attr and hasattr(settings, env_attr) and getattr(settings, env_attr, ""))
    custom_provider = any(
        cp["id"] == provider_id and cp.get("api_key", "")
        for cp in _load_raw().get("custom_providers", [])
    )

    if stored_ui:
        source = "ui"
    elif has_env:
        source = "env"
    elif key and custom_provider:
        source = "custom_provider"
    elif key:
        source = "fallback"
    else:
        source = "none"

    return {
        "provider_id": provider_id,
        "provider_name": provider.get("name", provider_id),
        "model_id": provider.get("active_model_id", ""),
        "has_key": bool(key),
        "key_masked": masked,
        "key_source": source,
        "configured": bool(key),
    }


# ─── API pública ────────────────────────────────────────────────────

def _apply_builtin_provider_overrides(provider_id: str, provider: dict, raw: dict | None = None) -> dict:
    """Aplica overrides salvos para provider built-in sem editar BUILTIN_PROVIDERS hardcoded."""
    raw = raw or _load_raw()
    override = raw.get("builtin_provider_overrides", {}).get(provider_id, {})
    merged = dict(provider)
    if isinstance(override, dict):
        merged.update({k: v for k, v in override.items() if k in {"enabled"}})
    return merged


def _apply_builtin_model_overrides(
    provider_id: str,
    models: list[dict],
    raw: dict | None = None,
    *,
    enrich_catalog: bool = True,
) -> list[dict]:
    """Aplica overrides salvos para modelos built-in sem editar BUILTIN_PROVIDERS hardcoded."""
    raw = raw or _load_raw()
    overrides = raw.get("builtin_model_overrides", {}).get(provider_id, {})
    dynamic = raw.get("builtin_dynamic_models", {}).get(provider_id)
    source_models = dynamic if isinstance(dynamic, list) and dynamic else models
    result = []
    for model in source_models:
        merged = dict(model)
        override = overrides.get(model.get("id"), {})
        if isinstance(override, dict):
            merged.update({k: v for k, v in override.items() if k in {"name", "context_length", "enabled"}})
        result.append(merged)
    if enrich_catalog:
        from src.core.model_catalog import enrich_builtin_models
        return enrich_builtin_models(provider_id, result)
    return result


def set_builtin_dynamic_models(provider_id: str, models: list[dict]) -> list[dict]:
    """Persist a provider-discovered catalog while retaining built-in semantics."""
    if provider_id not in BUILTIN_PROVIDERS:
        raise ValueError("Provider built-in desconhecido")
    normalized = []
    for model in models:
        model_id = str(model.get("id") or "").strip()
        if not model_id:
            continue
        normalized.append({
            **{k: v for k, v in model.items() if k not in {"api_key", "access_token", "refresh_token"}},
            "id": model_id,
            "name": str(model.get("name") or model_id),
            "context_length": int(model.get("context_length") or 1000000),
            "enabled": bool(model.get("enabled", True)),
        })
    raw = _load_raw()
    raw.setdefault("builtin_dynamic_models", {})[provider_id] = normalized
    _save_raw(raw)
    return normalized


def sync_models_from_catalog(provider_id: str, catalog_provider_id: str = "") -> dict:
    """Reconcilia um provider com uma unica fonte models.dev, sem misturar catalogos."""
    from src.core.model_catalog import resolve_catalog_provider_id

    if provider_id in {"ollama", "codex-chatgpt", "antigravity", "grok-oauth"}:
        raise ValueError("Este provider usa descoberta propria da conta ou maquina e nao deve ser substituido pelo catalogo mundial")
    provider = get_provider(provider_id)
    if not provider:
        raise ValueError("Provider nao encontrado")
    requested_source_id = str(catalog_provider_id or "").strip()
    declared_source_id = str(
        provider.get("catalog_provider_id")
        or resolve_catalog_provider_id(provider_id)
        or ""
    ).strip()
    if requested_source_id and declared_source_id and requested_source_id != declared_source_id:
        raise ValueError(
            "A fonte solicitada nao corresponde ao catalogo vinculado a este provider"
        )
    source_id = requested_source_id or declared_source_id
    if not source_id:
        raise ValueError("Este provider ainda nao possui uma fonte correspondente no models.dev")
    raw = _load_raw()
    if provider_id in BUILTIN_PROVIDERS:
        current_models = raw.get("builtin_dynamic_models", {}).get(provider_id)
        if not isinstance(current_models, list) or not current_models:
            current_models = BUILTIN_PROVIDERS[provider_id].get("models", [])
        merged, integrity = _reconcile_catalog_models(source_id, current_models)
        raw.setdefault("builtin_dynamic_models", {})[provider_id] = merged
    else:
        target = next((item for item in raw.get("custom_providers", []) if item.get("id") == provider_id), None)
        if target is None:
            raise ValueError("Provider nao pode receber sincronizacao de catalogo")
        merged, integrity = _reconcile_catalog_models(source_id, target.get("models", []))
        target["models"] = merged
        target["catalog_provider_id"] = source_id
    active_model_repaired = _repair_active_model_reference(raw, provider_id, merged)
    _save_raw(raw)

    return {
        "provider_id": provider_id,
        "catalog_provider_id": source_id,
        "total": len(merged),
        "added_hidden": integrity["added_hidden"],
        "removed_hidden": integrity["removed_catalog_models"],
        "preserved_manual": integrity["preserved_manual"],
        "active_model_repaired": active_model_repaired,
        "models": get_provider(provider_id).get("models", []),
    }


def list_providers(include_keys: bool = False, *, enrich_catalog: bool = True) -> list[dict]:
    """Retorna lista combinada de providers built-in + custom."""
    data = _load_raw()
    custom_providers = data.get("custom_providers", [])
    active_id = data.get("active_provider_id", "opencode-zen-free")
    active_model_id = data.get("active_model_id")

    result = []

    # Built-in
    for pid, builtin_info in BUILTIN_PROVIDERS.items():
        pinfo = _apply_builtin_provider_overrides(pid, builtin_info, data)
        models = _apply_builtin_model_overrides(
            pid, pinfo.get("models", []), data, enrich_catalog=enrich_catalog
        )
        marked_models = _mark_active_model(models, active_model_id, pid == active_id)
        effective_model_id = next((m["id"] for m in marked_models if m.get("active")), None)
        entry = {
            "id": pid,
            "name": pinfo["name"],
            "base_url": pinfo["base_url"],
            "endpoint": pinfo.get("endpoint", ""),
            "api_format": pinfo.get("api_format", "chat_completions"),
            "provider_type": "builtin",
            "enabled": pinfo.get("enabled", True),
            "models": marked_models,
            "active": pid == active_id,
            "active_model_id": effective_model_id if pid == active_id else None,
            **PROVIDER_RESOURCES.get(pid, {}),
        }
        # built-in: API key para providers comuns; OAuth pool para Codex
        actual_key = get_provider_api_key(pid)
        if pid in {"codex-chatgpt", "antigravity", "grok-oauth"}:
            has_accounts = _codex_has_accounts() if pid == "codex-chatgpt" else _antigravity_has_accounts()
            entry["api_key"] = ""
            entry["has_key"] = has_accounts
            entry["key_source"] = "oauth_pool" if has_accounts else "none"
        else:
            entry["api_key"] = actual_key if include_keys else ("sk-..." if actual_key else "")
            entry["has_key"] = bool(actual_key)
            entry["key_source"] = _get_key_source(pid, actual_key)
        result.append(entry)

    # Custom
    for cp in custom_providers:
        if enrich_catalog:
            from src.core.model_catalog import enrich_builtin_models
            models = enrich_builtin_models(cp["id"], cp.get("models", []))
        else:
            models = [dict(model) for model in cp.get("models", [])]
        marked_models = _mark_active_model(models, active_model_id, cp["id"] == active_id)
        effective_model_id = next((m["id"] for m in marked_models if m.get("active")), None)
        cp_key = get_provider_api_key(cp["id"])
        promoted_builtin = cp["id"] in PROMOTED_BUILTIN_PROVIDER_IDS
        entry = {
            "id": cp["id"],
            "name": cp.get("name", cp["id"]),
            "base_url": cp.get("base_url", ""),
            "endpoint": cp.get("endpoint", ""),
            "api_key": cp_key if include_keys else ("sk-..." if cp_key else ""),
            "api_format": cp.get("api_format", "chat_completions"),
            "auth_type": cp.get("auth_type", ""),
            "provider_type": "builtin" if promoted_builtin else "custom",
            "enabled": cp.get("enabled", True),
            "models": marked_models,
            "active": cp["id"] == active_id,
            "active_model_id": effective_model_id if cp["id"] == active_id else None,
            "has_key": bool(cp_key),
            "key_source": _get_key_source(cp["id"], cp_key),
            "reasoning_style": cp.get("reasoning_style", ""),
            "catalog_provider_id": cp.get("catalog_provider_id", ""),
            **PROVIDER_RESOURCES.get(cp["id"], {}),
        }
        result.append(entry)

    return result


def _mark_active_model(models: list[dict], active_model_id: str | None, is_active_provider: bool) -> list[dict]:
    """Marca qual modelo está ativo dentro de um provider.
    Só modelo habilitado pode ficar ativo.
    """
    if not is_active_provider or not models:
        return [dict(m, active=False) for m in models]

    enabled_models = [m for m in models if m.get("enabled", True)]
    if not enabled_models:
        return [dict(m, active=False) for m in models]

    active_id = active_model_id if any(m["id"] == active_model_id and m.get("enabled", True) for m in models) else enabled_models[0]["id"]
    return [dict(m, active=(m["id"] == active_id)) for m in models]


def get_provider(provider_id: str, include_keys: bool = False) -> Optional[dict]:
    """Retorna um provider pelo ID."""
    for p in list_providers(include_keys=include_keys):
        if p["id"] == provider_id:
            return p
    return None


def export_custom_providers(include_api_keys: bool = False) -> list[dict]:
    """Exporta apenas providers customizados globais em formato portavel."""
    raw = _load_raw()
    exported = []
    for provider in raw.get("custom_providers", []):
        if provider.get("id") in PROMOTED_BUILTIN_PROVIDER_IDS:
            continue
        item = {
            "id": provider.get("id", ""),
            "name": provider.get("name", provider.get("id", "")),
            "base_url": provider.get("base_url", ""),
            "endpoint": provider.get("endpoint", ""),
            "api_format": provider.get("api_format", "chat_completions"),
            "enabled": bool(provider.get("enabled", True)),
            "catalog_provider_id": provider.get("catalog_provider_id", ""),
            "models": [
                {
                    key: value
                    for key, value in model.items()
                    if key not in {"api_key", "access_token", "refresh_token"}
                }
                for model in provider.get("models", [])
                if isinstance(model, dict)
            ],
        }
        if provider.get("reasoning_style"):
            item["reasoning_style"] = provider["reasoning_style"]
        if include_api_keys:
            item["api_key"] = get_provider_api_key(str(provider.get("id", "")))
        exported.append(item)
    return exported


def _normalize_import_models(value) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("models deve ser uma lista")
    if len(value) > 500:
        raise ValueError("Cada provider pode importar no maximo 500 modelos")

    models = []
    seen_ids = set()
    for raw_model in value:
        if not isinstance(raw_model, dict):
            raise ValueError("Cada modelo importado deve ser um objeto JSON")
        model_id = str(raw_model.get("id", "")).strip()
        if not model_id:
            raise ValueError("Todo modelo importado precisa de id")
        if model_id in seen_ids:
            raise ValueError(f"Modelo duplicado no provider: {model_id}")
        seen_ids.add(model_id)
        model = {
            key: value
            for key, value in raw_model.items()
            if key not in {"active", "api_key", "access_token", "refresh_token"}
        }
        model["id"] = model_id
        model["name"] = str(raw_model.get("name", model_id)).strip() or model_id
        try:
            model["context_length"] = max(1, int(raw_model.get("context_length", 128000)))
        except (TypeError, ValueError):
            model["context_length"] = 128000
        model["enabled"] = bool(raw_model.get("enabled", True))
        models.append(model)
    return models


def _reconcile_catalog_models(
    catalog_provider_id: str,
    current_models,
) -> tuple[list[dict], dict]:
    """Reconstroi modelos catalogados a partir da fonte oficial e preserva apenas dados locais seguros."""
    from src.core.model_catalog import get_catalog, list_catalog_models

    source_id = str(catalog_provider_id or "").strip()
    if not source_id or source_id not in get_catalog():
        raise ValueError("Provider nao encontrado no catalogo mundial")

    incoming = list_catalog_models(source_id)
    if not incoming:
        raise ValueError("O provider escolhido nao possui modelos no catalogo atual")

    normalized_current = _normalize_import_models(current_models or [])
    existing = {str(model.get("id")): dict(model) for model in normalized_current}
    merged = []
    added = 0

    for catalog_model in incoming:
        model_id = str(catalog_model["id"])
        previous = existing.pop(model_id, None)
        if previous:
            model = {**catalog_model, **previous}
        else:
            model = {**catalog_model, "enabled": False}
            added += 1
        model.pop("active", None)
        model["catalog_source"] = "models.dev"
        model["catalog_provider_id"] = source_id
        model["catalog_removed"] = False
        merged.append(model)

    removed_catalog_models = 0
    preserved_manual = 0
    for previous in existing.values():
        previous.pop("active", None)
        previous_source = str(previous.get("catalog_provider_id") or "").strip()
        catalog_generated = bool(
            previous_source
            or str(previous.get("catalog_source") or "").startswith("models.dev")
            or previous.get("catalog_removed")
        )
        if not catalog_generated:
            previous.pop("catalog_removed", None)
            merged.append(previous)
            preserved_manual += 1
            continue

        # Um modelo explicitamente ligado a esta mesma fonte pode ter sido
        # retirado do catalogo, mas continuamos preservando-o se o admin o
        # habilitou. Modelos ocultos, sem fonte especifica ou de outra fonte
        # sao residuos seguros de remover e eram a origem da contaminacao.
        if previous_source == source_id and previous.get("enabled"):
            previous["catalog_removed"] = True
            merged.append(previous)
            continue
        removed_catalog_models += 1

    return merged, {
        "added_hidden": added,
        "removed_catalog_models": removed_catalog_models,
        "preserved_manual": preserved_manual,
    }


def _repair_active_model_reference(raw: dict, provider_id: str, models: list[dict]) -> bool:
    """Mantem o modelo ativo valido depois de remover residuos de outro catalogo."""
    if raw.get("active_provider_id") != provider_id:
        return False
    active_model_id = str(raw.get("active_model_id") or "")
    if any(
        str(model.get("id") or "") == active_model_id and model.get("enabled", True)
        for model in models
    ):
        return False
    fallback = next((model for model in models if model.get("enabled", True)), None)
    if fallback is None and models:
        fallback = models[0]
        fallback["enabled"] = True
    next_model_id = str(fallback.get("id") or "") if fallback else None
    changed = raw.get("active_model_id") != next_model_id
    raw["active_model_id"] = next_model_id
    return changed


def repair_catalog_integrity() -> dict:
    """Repara todos os custom providers catalogados uma vez, sem tocar nos modelos manuais."""
    raw = _load_raw()
    repaired = []
    errors = []
    removed_catalog_models = 0
    preserved_manual = 0

    for provider in raw.get("custom_providers", []):
        provider_id = str(provider.get("id") or "")
        source_id = str(provider.get("catalog_provider_id") or "").strip()
        if not provider_id or not source_id:
            continue
        try:
            models, integrity = _reconcile_catalog_models(
                source_id,
                provider.get("models", []),
            )
        except ValueError as exc:
            errors.append({"provider_id": provider_id, "error": str(exc)})
            continue
        models_changed = models != provider.get("models", [])
        active_model_repaired = _repair_active_model_reference(raw, provider_id, models)
        if models_changed or active_model_repaired:
            provider["models"] = models
            repaired.append(provider_id)
        removed_catalog_models += integrity["removed_catalog_models"]
        preserved_manual += integrity["preserved_manual"]

    if repaired:
        _save_raw(raw)
    return {
        "repaired": repaired,
        "removed_catalog_models": removed_catalog_models,
        "preserved_manual": preserved_manual,
        "errors": errors,
    }


def import_custom_providers(items: list[dict]) -> dict:
    """Mescla providers customizados globais por ID sem alterar o provider ativo."""
    if not isinstance(items, list):
        raise ValueError("custom_providers deve ser uma lista")
    if len(items) > 100:
        raise ValueError("O arquivo pode importar no maximo 100 providers customizados")

    raw = _load_raw()
    custom = raw.setdefault("custom_providers", [])
    by_id = {str(provider.get("id", "")): provider for provider in custom}
    created = []
    updated = []
    skipped = []
    keys_imported = 0

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Cada provider importado deve ser um objeto JSON")
        provider_id = str(item.get("id", "")).strip().lower().replace(" ", "-")
        if not provider_id:
            raise ValueError("Todo provider customizado importado precisa de id")
        if provider_id in BUILTIN_PROVIDERS or provider_id in PROMOTED_BUILTIN_PROVIDER_IDS:
            skipped.append({"id": provider_id, "reason": "provider built-in"})
            continue

        existing = by_id.get(provider_id)
        provider = dict(existing or {})
        provider["id"] = provider_id
        provider["name"] = str(item.get("name", provider.get("name", provider_id))).strip() or provider_id
        if "base_url" in item or not existing:
            provider["base_url"] = str(item.get("base_url", "")).strip()
        if "endpoint" in item or not existing:
            provider["endpoint"] = str(item.get("endpoint", "")).strip()
        if "api_format" in item or not existing:
            provider["api_format"] = str(item.get("api_format", "chat_completions")).strip() or "chat_completions"
        if "auth_type" in item or not existing:
            provider["auth_type"] = str(item.get("auth_type", "")).strip()
        if "enabled" in item or not existing:
            requested_enabled = bool(item.get("enabled", True))
            if raw.get("active_provider_id") == provider_id and not requested_enabled:
                requested_enabled = True
            provider["enabled"] = requested_enabled
        if "models" in item or not existing:
            provider["models"] = _normalize_import_models(item.get("models", []))
        if "reasoning_style" in item:
            provider["reasoning_style"] = str(item.get("reasoning_style", "")).strip()
        if "catalog_provider_id" in item:
            provider["catalog_provider_id"] = str(item.get("catalog_provider_id", "")).strip()
        if provider.get("catalog_provider_id"):
            provider["models"], _ = _reconcile_catalog_models(
                provider["catalog_provider_id"],
                provider.get("models", []),
            )
            _repair_active_model_reference(raw, provider_id, provider["models"])
        provider["created_at"] = provider.get("created_at") or datetime.now(timezone.utc).isoformat()

        if "api_key" in item:
            api_key = str(item.get("api_key", ""))
            provider["api_key"] = api_key
            if api_key:
                raw.setdefault("provider_keys", {})[provider_id] = api_key
                keys_imported += 1
            else:
                raw.setdefault("provider_keys", {}).pop(provider_id, None)

        if existing:
            index = custom.index(existing)
            custom[index] = provider
            updated.append(provider_id)
        else:
            custom.append(provider)
            created.append(provider_id)
        by_id[provider_id] = provider

    raw["custom_providers"] = custom
    _save_raw(raw)
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "keys_imported": keys_imported,
    }


def get_active_model_metadata() -> dict:
    """Snapshot do provider/model efetivamente ativo para salvar junto da resposta."""
    cfg = get_active_config()
    return {
        "provider_id": cfg.get("provider_id", ""),
        "provider_name": cfg.get("name", cfg.get("provider_id", "")),
        "model_id": cfg.get("model_id", ""),
        "model_name": cfg.get("model_name", cfg.get("model_id", "")),
    }


def create_provider(body: dict) -> dict:
    """Cria um novo provider customizado."""
    raw = _load_raw()
    custom = raw["custom_providers"]

    # Gera ID a partir do nome ou do campo id
    raw_id = body.get("id", "").strip()
    raw_name = body.get("name", "").strip()
    if not raw_id and raw_name:
        provider_id = raw_name.lower().replace(" ", "-").replace("/", "-")
    elif raw_id:
        provider_id = raw_id.lower().replace(" ", "-")
    else:
        provider_id = "provider-" + str(len(custom) + 1)

    if provider_id in BUILTIN_PROVIDERS or provider_id in PROMOTED_BUILTIN_PROVIDER_IDS:
        raise ValueError(f"Provider built-in '{provider_id}' ja existe")

    # Verifica se já existe
    for cp in custom:
        if cp["id"] == provider_id:
            raise ValueError(f"Provider '{provider_id}' já existe")

    catalog_provider_id = str(body.get("catalog_provider_id", "")).strip()
    models = _normalize_import_models(body.get("models", []))
    if catalog_provider_id:
        models, _ = _reconcile_catalog_models(catalog_provider_id, models)

    new_provider = {
        "id": provider_id,
        "name": body.get("name", provider_id),
        "base_url": body.get("base_url", ""),
        "endpoint": body.get("endpoint", ""),
        "api_key": body.get("api_key", ""),
        "api_format": body.get("api_format", "chat_completions"),
        "auth_type": str(body.get("auth_type", "")).strip(),
        "enabled": body.get("enabled", True),
        "models": models,
        "catalog_provider_id": catalog_provider_id,
        "created_at": datetime.utcnow().isoformat(),
    }

    custom.append(new_provider)
    _save_raw(raw)

    return {
        "id": provider_id,
        "name": new_provider["name"],
        "base_url": new_provider["base_url"],
        "endpoint": new_provider["endpoint"],
        "api_format": new_provider["api_format"],
        "auth_type": new_provider["auth_type"],
        "provider_type": "custom",
        "enabled": new_provider["enabled"],
        "models": new_provider["models"],
        "catalog_provider_id": new_provider["catalog_provider_id"],
        "active": False,
    }


def set_api_key_for_provider(provider_id: str, api_key: str) -> bool:
    """Salva chave de API para qualquer provider (built-in ou custom)."""
    return set_stored_api_key(provider_id, api_key)


def update_provider(provider_id: str, data: dict) -> Optional[dict]:
    """Atualiza um provider. Built-in salva override persistente; custom altera o registro."""
    # Se veio api_key, salva também no provider_keys
    if "api_key" in data:
        set_stored_api_key(provider_id, data["api_key"])
    raw = _load_raw()

    if provider_id in PROMOTED_BUILTIN_PROVIDER_IDS:
        forbidden = set(data) - {"enabled", "api_key"}
        if forbidden:
            raise ValueError("Provider built-in nao permite editar sua configuracao base")
        custom = raw["custom_providers"]
        for cp in custom:
            if cp["id"] != provider_id:
                continue
            if data.get("enabled") is False and raw.get("active_provider_id") == provider_id:
                raise ValueError("Nao da para desativar o provider ativo. Ative outro provider primeiro.")
            if "enabled" in data:
                cp["enabled"] = data["enabled"]
            _save_raw(raw)
            return get_provider(provider_id)
        return None

    # Built-in: persiste enable/disable em providers.json.
    if provider_id in BUILTIN_PROVIDERS:
        if data.get("enabled") is False and raw.get("active_provider_id") == provider_id:
            raise ValueError("Não dá para desativar o provider ativo. Ative outro provider primeiro.")
        raw.setdefault("builtin_provider_overrides", {})
        raw["builtin_provider_overrides"].setdefault(provider_id, {})
        if "enabled" in data:
            raw["builtin_provider_overrides"][provider_id]["enabled"] = data["enabled"]
        _save_raw(raw)
        return get_provider(provider_id)

    custom = raw["custom_providers"]

    for i, cp in enumerate(custom):
        if cp["id"] == provider_id:
            # Atualiza campos
            if "name" in data:
                cp["name"] = data["name"]
            if "base_url" in data:
                cp["base_url"] = data["base_url"]
            if "endpoint" in data:
                cp["endpoint"] = data["endpoint"]
            if "api_key" in data and data["api_key"]:
                cp["api_key"] = data["api_key"]
            if "api_format" in data:
                cp["api_format"] = data["api_format"]
            if "auth_type" in data:
                cp["auth_type"] = str(data["auth_type"] or "").strip()
            if "enabled" in data:
                if data["enabled"] is False and raw.get("active_provider_id") == provider_id:
                    raise ValueError("Não dá para desativar o provider ativo. Ative outro provider primeiro.")
                cp["enabled"] = data["enabled"]

            custom[i] = cp
            raw["custom_providers"] = custom
            _save_raw(raw)
            return get_provider(provider_id)

    return None


def delete_provider(provider_id: str) -> bool:
    """Remove um provider customizado."""
    if provider_id in BUILTIN_PROVIDERS or provider_id in PROMOTED_BUILTIN_PROVIDER_IDS:
        return False
    raw = _load_raw()
    before = len(raw["custom_providers"])
    raw["custom_providers"] = [cp for cp in raw["custom_providers"] if cp["id"] != provider_id]

    if len(raw["custom_providers"]) < before:
        # Se o provider ativo foi deletado, volta pro default
        if raw.get("active_provider_id") == provider_id:
            raw["active_provider_id"] = "opencode-zen-free"
        _save_raw(raw)
        return True
    return False


def set_active_provider(provider_id: str) -> bool:
    """Define o provider ativo."""
    # Verifica se existe (built-in ou custom) e está habilitado
    exists = get_provider(provider_id)
    if not exists or not exists.get("enabled", True):
        return False

    raw = _load_raw()
    raw["active_provider_id"] = provider_id
    # Reseta o modelo ativo ao trocar de provider
    raw["active_model_id"] = None
    _save_raw(raw)
    return True


def set_active_model(model_id: str) -> bool:
    """Define o modelo ativo dentro do provider ativo."""
    raw = _load_raw()
    active_id = raw.get("active_provider_id", "opencode-zen-free")
    provider = get_provider(active_id)
    if not provider:
        return False
    # Verifica se o modelo existe e está habilitado no provider
    for m in provider.get("models", []):
        if m["id"] == model_id and m.get("enabled", True):
            raw["active_model_id"] = model_id
            _save_raw(raw)
            return True
    return False


def get_active_config(provider_id: str | None = None, model_id: str | None = None) -> dict:
    """Retorna a configuração completa do provider+modelo ativos.
    Usado pelo chat para saber qual modelo usar.
    """
    raw = _load_raw()
    explicit_provider = bool(provider_id)
    active_id = provider_id or raw.get("active_provider_id", "opencode-zen-free")
    active_model_id = model_id if explicit_provider else raw.get("active_model_id")

    # Repara config antiga/inválida: provider desativado ou sem modelo habilitado.
    active_provider = get_provider(active_id)
    if not active_provider or not active_provider.get("enabled", True) or not any(m.get("enabled", True) for m in active_provider.get("models", [])):
        fallback = next((p for p in list_providers() if p.get("enabled", True) and any(m.get("enabled", True) for m in p.get("models", []))), None)
        if fallback and not explicit_provider:
            active_id = fallback["id"]
            raw["active_provider_id"] = active_id
            raw["active_model_id"] = None
            active_model_id = None
            _save_raw(raw)

    # Tenta built-in primeiro
    if active_id in BUILTIN_PROVIDERS:
        pinfo = BUILTIN_PROVIDERS[active_id]
        models = _apply_builtin_model_overrides(active_id, pinfo.get("models", []), raw)
        model_info = None
        if active_model_id:
            model_info = next((m for m in models if m["id"] == active_model_id and m.get("enabled", True)), None)
        if not model_info and models:
            model_info = next((m for m in models if m.get("enabled", True)), None)
        config = {
            "provider_id": active_id,
            "name": pinfo["name"],
            "base_url": pinfo.get("base_url", ""),
            "endpoint": pinfo.get("endpoint", ""),
            "api_key": get_provider_api_key(active_id),
            "api_format": pinfo.get("api_format", "chat_completions"),
            "model_id": model_info["id"] if model_info else "",
            "model_name": model_info["name"] if model_info else "",
            "supports_images": model_info.get("supports_images") if model_info else None,
            "supports_thinking": model_info.get("supports_thinking") if model_info else None,
            "image_generation": bool(model_info.get("image_generation")) if model_info else False,
            "supports_tools": model_info.get("supports_tools") if model_info else None,
            "reasoning_style": pinfo.get("reasoning_style", ""),
        }
        from src.core.model_capabilities import with_reasoning_capabilities
        return with_reasoning_capabilities(config)

    # Tenta custom
    for cp in raw.get("custom_providers", []):
        if cp["id"] == active_id:
            from src.core.model_catalog import enrich_builtin_models
            models = enrich_builtin_models(active_id, cp.get("models", []))
            model_info = None
            if active_model_id:
                model_info = next((m for m in models if m["id"] == active_model_id and m.get("enabled", True)), None)
            if not model_info and models:
                model_info = next((m for m in models if m.get("enabled", True)), None)
            config = {
                "provider_id": active_id,
                "name": cp.get("name", active_id),
                "base_url": cp.get("base_url", ""),
                "endpoint": cp.get("endpoint", ""),
                "api_key": get_provider_api_key(active_id),
                "api_format": cp.get("api_format", "chat_completions"),
                "auth_type": cp.get("auth_type", ""),
                "model_id": model_info["id"] if model_info else "",
                "model_name": model_info["name"] if model_info else "",
                "supports_images": model_info.get("supports_images") if model_info else None,
                "supports_thinking": model_info.get("supports_thinking") if model_info else None,
                "image_generation": bool(model_info.get("image_generation")) if model_info else False,
                "supports_tools": model_info.get("supports_tools") if model_info else None,
                "reasoning_style": cp.get("reasoning_style", ""),
                "reasoning_options": model_info.get("reasoning_options", []) if model_info else [],
            }
            from src.core.model_capabilities import with_reasoning_capabilities
            return with_reasoning_capabilities(config)

    # Fallback para settings existentes
    return {
        "provider_id": active_id,
        "name": active_id,
        "base_url": "",
        "api_key": "",
        "api_format": "chat_completions",
        "model_id": "",
        "model_name": "",
    }


def export_complete_state() -> dict:
    """Retorna o estado portavel completo, incluindo chaves globais."""
    raw = deepcopy(_load_raw())
    for key, default in DEFAULT_PROVIDERS_DATA.items():
        raw.setdefault(key, deepcopy(default))
    # Materializa tambem chaves vindas de env/settings. Assim o backup continua
    # portavel mesmo quando a credencial nao foi originalmente digitada na UI.
    for provider in list_providers(include_keys=False):
        provider_id = str(provider.get("id") or "")
        effective_key = get_provider_api_key(provider_id)
        if provider_id and effective_key:
            raw["provider_keys"][provider_id] = effective_key
    return raw


def import_complete_state(state: dict) -> dict:
    """Restaura um estado completo validado, sem aceitar campos arbitrarios."""
    if not isinstance(state, dict):
        raise ValueError("Estado de providers invalido")
    allowed = set(DEFAULT_PROVIDERS_DATA)
    restored = deepcopy(DEFAULT_PROVIDERS_DATA)
    for key in allowed:
        if key in state:
            restored[key] = deepcopy(state[key])
    if not isinstance(restored["custom_providers"], list):
        raise ValueError("Lista de providers customizados invalida")
    for key in ("provider_keys", "builtin_provider_overrides", "builtin_model_overrides", "builtin_dynamic_models"):
        if not isinstance(restored[key], dict):
            raise ValueError(f"Campo {key} invalido")
    if not isinstance(restored["active_provider_id"], str):
        raise ValueError("Provider ativo invalido")
    if restored["active_model_id"] is not None and not isinstance(restored["active_model_id"], str):
        raise ValueError("Modelo ativo invalido")
    for provider in restored["custom_providers"]:
        if not isinstance(provider, dict):
            raise ValueError("Provider customizado invalido")
        provider_id = str(provider.get("id") or "").strip()
        source_id = str(provider.get("catalog_provider_id") or "").strip()
        if not provider_id:
            raise ValueError("Provider customizado sem id")
        if source_id:
            provider["models"], _ = _reconcile_catalog_models(
                source_id,
                provider.get("models", []),
            )
            _repair_active_model_reference(restored, provider_id, provider["models"])
    _save_raw(restored)
    return {
        "providers": len(restored["custom_providers"]) + len(BUILTIN_PROVIDERS),
        "keys": sum(1 for value in restored["provider_keys"].values() if value),
    }


def add_model(provider_id: str, model_data: dict) -> Optional[dict]:
    """Adiciona um modelo a um provider."""
    raw = _load_raw()
    custom = raw["custom_providers"]

    # Primeiro tenta nos custom
    for cp in custom:
        if cp["id"] == provider_id:
            model_id = model_data.get("id", "").strip().lower().replace(" ", "-")
            if not model_id:
                model_id = "model-" + str(len(cp.get("models", [])) + 1)

            new_model = {
                "id": model_id,
                "name": model_data.get("name", model_id),
                "context_length": model_data.get("context_length", 128000),
                "enabled": model_data.get("enabled", True),
            }

            if "models" not in cp:
                cp["models"] = []
            cp["models"].append(new_model)
            _save_raw(raw)
            return new_model

    # Se for built-in, não permite (a menos que queira)
    if provider_id in BUILTIN_PROVIDERS:
        return None  # Built-in não pode ser modificado

    return None


def update_model(provider_id: str, model_id: str, data: dict) -> Optional[dict]:
    """Atualiza um modelo. Para built-in, salva override em providers.json."""
    raw = _load_raw()

    # Built-in: não altera BUILTIN_PROVIDERS; salva override persistente.
    if provider_id in BUILTIN_PROVIDERS:
        dynamic_models = raw.get("builtin_dynamic_models", {}).get(provider_id)
        base_models = (
            dynamic_models
            if isinstance(dynamic_models, list) and dynamic_models
            else BUILTIN_PROVIDERS[provider_id].get("models", [])
        )
        base = next((m for m in base_models if m["id"] == model_id), None)
        if not base:
            return None

        raw.setdefault("builtin_model_overrides", {})
        raw["builtin_model_overrides"].setdefault(provider_id, {})
        override = raw["builtin_model_overrides"][provider_id].setdefault(model_id, {})
        for key in (
            "name", "context_length", "enabled", "validation_status",
            "validation_error", "validated_at", "validation_latency_ms",
        ):
            if key in data:
                override[key] = data[key]

        # Não permite desativar o modelo ativo; o usuário precisa selecionar outro antes.
        if data.get("enabled") is False and raw.get("active_provider_id") == provider_id and raw.get("active_model_id") == model_id:
            raise ValueError("Não dá para desativar o modelo ativo. Selecione outro modelo primeiro.")

        _save_raw(raw)
        merged = dict(base)
        merged.update(override)
        return merged

    # Custom providers
    for cp in raw["custom_providers"]:
        if cp["id"] == provider_id:
            for mi, m in enumerate(cp.get("models", [])):
                if m["id"] == model_id:
                    if "name" in data:
                        m["name"] = data["name"]
                    if "context_length" in data:
                        m["context_length"] = data["context_length"]
                    if "enabled" in data:
                        m["enabled"] = data["enabled"]
                    for key in (
                        "validation_status", "validation_error", "validated_at",
                        "validation_latency_ms",
                    ):
                        if key in data:
                            m[key] = data[key]
                    if data.get("enabled") is False and raw.get("active_provider_id") == provider_id and raw.get("active_model_id") == model_id:
                        raise ValueError("Não dá para desativar o modelo ativo. Selecione outro modelo primeiro.")
                    cp["models"][mi] = m
                    _save_raw(raw)
                    return dict(m)
    return None


def delete_model(provider_id: str, model_id: str) -> bool:
    """Remove um modelo de um provider custom."""
    raw = _load_raw()
    for cp in raw["custom_providers"]:
        if cp["id"] == provider_id:
            before = len(cp.get("models", []))
            cp["models"] = [m for m in cp.get("models", []) if m["id"] != model_id]
            if len(cp["models"]) < before:
                _save_raw(raw)
                return True
    return False
