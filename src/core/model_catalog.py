"""Capability metadata for built-in models, sourced from the OpenCode catalog.

OpenCode uses models.dev for provider/model capabilities.  We keep a small disk
cache so the provider manager is fast and remains usable when models.dev is
temporarily unavailable.
"""

from __future__ import annotations

import json
import os
import threading
import time
from urllib.request import Request, urlopen


CATALOG_URL = "https://models.dev/api.json"
CACHE_FILE = os.path.join(".", "data", "models-dev-cache.json")
CACHE_TTL_SECONDS = 24 * 60 * 60

_lock = threading.Lock()
_catalog: dict | None = None

# Models explicitly recommended in OpenCode's model guide.  models.dev itself
# describes capabilities but intentionally has no model-level recommendation.
OPENCODE_RECOMMENDED = {
    "gpt-5.2",
    "gpt-5.1-codex",
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "minimax-m2.1",
    "gemini-3-pro",
    "gemini-3-pro-preview",
}

PROVIDER_CATALOG_IDS = {
    "opencode-go": ("opencode-go", "opencode"),
    "opencode-zen": ("opencode",),
    "opencode-zen-free": ("opencode",),
    "openai": ("openai", "opencode"),
    "anthropic": ("anthropic", "opencode"),
    "codex-chatgpt": ("openai", "opencode"),
}

# Compact snapshot of the fields used by this UI. It is only consulted when a
# model cannot be resolved from the live/stale models.dev catalog.
# Tuple: images, thinking, video, audio, pdf, tools.
FALLBACK_CAPABILITIES = {
    "big-pickle": (False, True, False, False, False, True),
    "chatgpt-4o-latest": (True, False, False, False, False, False),
    "claude-fable-5": (True, True, False, False, True, True),
    "claude-haiku-4-5": (True, True, False, False, True, True),
    "claude-opus-4-5": (True, True, False, False, True, True),
    "claude-opus-4-6": (True, True, False, False, True, True),
    "claude-opus-4-7": (True, True, False, False, True, True),
    "claude-opus-4-8": (True, True, False, False, True, True),
    "claude-sonnet-4-5": (True, True, False, False, True, True),
    "claude-sonnet-4-6": (True, True, False, False, True, True),
    "claude-sonnet-5": (True, True, False, False, True, True),
    "deepseek-v4-flash": (False, True, False, False, False, True),
    "deepseek-v4-flash-free": (False, True, False, False, False, True),
    "deepseek-v4-pro": (False, True, False, False, False, True),
    "gemini-3-flash": (True, True, True, True, True, True),
    "gemini-3.1-pro": (True, True, True, True, True, True),
    "gemini-3.5-flash": (True, True, True, True, True, True),
    "glm-5": (False, True, False, False, False, True),
    "glm-5.1": (False, True, False, False, False, True),
    "glm-5.2": (False, True, False, False, False, True),
    "gpt-4.1": (True, False, False, False, True, True),
    "gpt-4.1-mini": (True, False, False, False, True, True),
    "gpt-4.1-nano": (True, False, False, False, False, True),
    "gpt-5": (True, True, False, False, False, True),
    "gpt-5-codex": (True, True, False, False, False, True),
    "gpt-5-nano": (True, True, False, False, False, True),
    "gpt-5.1": (True, True, False, False, False, True),
    "gpt-5.1-codex": (True, True, False, False, False, True),
    "gpt-5.1-codex-max": (True, True, False, False, False, True),
    "gpt-5.1-codex-mini": (True, True, False, False, False, True),
    "gpt-5.2": (True, True, False, False, False, True),
    "gpt-5.2-codex": (True, True, False, False, True, True),
    "gpt-5.3-codex": (True, True, False, False, True, True),
    "gpt-5.3-codex-spark": (False, True, False, False, False, True),
    "gpt-5.4": (True, True, False, False, True, True),
    "gpt-5.4-mini": (True, True, False, False, True, True),
    "gpt-5.4-nano": (True, True, False, False, True, True),
    "gpt-5.4-pro": (True, True, False, False, True, True),
    "gpt-5.5": (True, True, False, False, True, True),
    "gpt-5.5-pro": (True, True, False, False, True, True),
    "gpt-5.6-luna": (True, True, False, False, True, True),
    "gpt-5.6-sol": (True, True, False, False, True, True),
    "gpt-5.6-terra": (True, True, False, False, True, True),
    "grok-build-0.1": (True, True, False, False, False, True),
    "kimi-k2.5": (True, True, True, False, False, True),
    "kimi-k2.6": (True, True, True, False, False, True),
    "kimi-k2.7-code": (True, True, True, False, False, True),
    "mimo-v2.5": (True, True, True, True, False, True),
    "mimo-v2.5-free": (True, True, True, True, False, True),
    "mimo-v2.5-pro": (False, True, False, False, False, True),
    "minimax-m2.5": (False, True, False, False, False, True),
    "minimax-m2.7": (False, True, False, False, False, True),
    "minimax-m3": (True, True, True, False, False, True),
    "nemotron-3-ultra-free": (False, True, False, False, False, True),
    "north-mini-code-free": (False, True, False, False, False, True),
    "qwen3.5-plus": (True, True, True, False, False, True),
    "qwen3.6-plus": (True, True, True, False, False, True),
    "qwen3.7-max": (False, True, False, False, False, True),
    "qwen3.7-plus": (True, True, True, False, False, True),
}


def _read_cache(*, allow_stale: bool) -> dict:
    try:
        age = time.time() - os.path.getmtime(CACHE_FILE)
        if not allow_stale and age > CACHE_TTL_SECONDS:
            return {}
        with open(CACHE_FILE, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _fetch_catalog() -> dict:
    request = Request(
        CATALOG_URL,
        headers={"Accept": "application/json", "User-Agent": "chatbot-provider-catalog/1.0"},
    )
    with urlopen(request, timeout=5) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError("Catalogo models.dev invalido")
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    temporary = CACHE_FILE + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False)
    os.replace(temporary, CACHE_FILE)
    return value


def get_catalog() -> dict:
    global _catalog
    if _catalog is not None:
        return _catalog
    with _lock:
        if _catalog is not None:
            return _catalog
        fresh = _read_cache(allow_stale=False)
        if fresh:
            _catalog = fresh
            return fresh
        try:
            _catalog = _fetch_catalog()
        except Exception:
            _catalog = _read_cache(allow_stale=True)
        return _catalog


def _candidate_ids(model: dict) -> list[str]:
    model_id = str(model.get("id") or "")
    candidates = [model_id]
    alias = str(model.get("alias") or "")
    if alias:
        candidates.append(alias)
    if model_id.endswith("-free"):
        candidates.append(model_id.removesuffix("-free"))
    if model_id.startswith("gpt-5.6-"):
        candidates.append("gpt-5.6")
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _find_metadata(provider_id: str, model: dict, catalog: dict) -> dict:
    for source_id in PROVIDER_CATALOG_IDS.get(provider_id, (provider_id,)):
        models = (catalog.get(source_id) or {}).get("models") or {}
        for candidate in _candidate_ids(model):
            value = models.get(candidate)
            if isinstance(value, dict):
                return value
    # Gateways occasionally publish a model before its preferred source mapping
    # is known. Exact-ID fallback still uses models.dev, never guessed metadata.
    for provider in catalog.values():
        models = provider.get("models") if isinstance(provider, dict) else None
        if not isinstance(models, dict):
            continue
        for candidate in _candidate_ids(model):
            value = models.get(candidate)
            if isinstance(value, dict):
                return value
    return {}


def enrich_builtin_models(provider_id: str, models: list[dict]) -> list[dict]:
    """Merge models.dev capabilities without overwriting provider-specific data."""
    if provider_id == "antigravity":
        result = []
        for original in models:
            model = dict(original)
            if model.get("supports_thinking"):
                model.setdefault("thinking_stream", "extra-low" not in str(model.get("id", "")).lower())
            result.append(model)
        return result
    catalog = get_catalog()
    result = []
    for original in models:
        model = dict(original)
        metadata = _find_metadata(provider_id, model, catalog) if catalog else {}
        if metadata:
            modalities = metadata.get("modalities") or {}
            inputs = modalities.get("input") or []
            model.setdefault("supports_images", "image" in inputs)
            model.setdefault("supports_video", "video" in inputs)
            model.setdefault("supports_audio", "audio" in inputs)
            model.setdefault("supports_pdf", "pdf" in inputs)
            model.setdefault("supports_thinking", bool(metadata.get("reasoning")))
            model.setdefault("supports_tools", bool(metadata.get("tool_call")))
            reasoning_options = metadata.get("reasoning_options")
            if isinstance(reasoning_options, list) and reasoning_options:
                model.setdefault("reasoning_options", reasoning_options)
            model.setdefault("catalog_source", "models.dev")
        else:
            fallback = next(
                (FALLBACK_CAPABILITIES.get(candidate) for candidate in _candidate_ids(model)
                 if candidate in FALLBACK_CAPABILITIES),
                None,
            )
            if fallback:
                images, thinking, video, audio, pdf, tools = fallback
                model.setdefault("supports_images", images)
                model.setdefault("supports_thinking", thinking)
                model.setdefault("supports_video", video)
                model.setdefault("supports_audio", audio)
                model.setdefault("supports_pdf", pdf)
                model.setdefault("supports_tools", tools)
                model.setdefault("catalog_source", "models.dev-snapshot")
        model.setdefault(
            "recommended",
            any(candidate in OPENCODE_RECOMMENDED for candidate in _candidate_ids(model)),
        )
        result.append(model)
    return result
