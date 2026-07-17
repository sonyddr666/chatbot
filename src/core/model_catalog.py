"""Capability metadata for built-in models, sourced from the OpenCode catalog.

OpenCode uses models.dev for provider/model capabilities.  We keep a small disk
cache so the provider manager is fast and remains usable when models.dev is
temporarily unavailable.
"""

from __future__ import annotations

import json
import os
from glob import glob
import threading
import time
from urllib.request import Request, urlopen


CATALOG_URL = "https://models.dev/api.json"
CACHE_FILE = os.path.join(".", "data", "models-dev-cache.json")
CATALOG_PROVIDER_DEFAULTS = {
    # models.dev does not currently publish this gateway URL, although the
    # provider documents a single OpenAI-compatible endpoint for all models.
    "aihubmix": {
        "api": "https://aihubmix.com/v1",
        "api_format": "chat_completions",
    },
}
CACHE_TTL_SECONDS = 24 * 60 * 60
CONNECTION_CATALOG_GLOB = os.path.join(".", "research", "provider_catalog", "*.json")

_lock = threading.Lock()
_catalog: dict | None = None
_catalog_loaded_at = 0.0


def _connection_catalog() -> dict[str, dict]:
    """Load reviewed connection contracts without making models.dev an endpoint authority."""
    result: dict[str, dict] = {}
    for path in sorted(glob(CONNECTION_CATALOG_GLOB)):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                items = json.load(handle)
        except (OSError, ValueError, TypeError):
            continue
        if isinstance(items, dict):
            items = items.get("providers")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            provider_id = str(item.get("provider_id") or "").strip()
            if not provider_id:
                continue
            ranks = {"low": 1, "medium": 2, "high": 3}
            incoming_rank = ranks.get(str(item.get("confidence") or "").lower(), 0)
            current_rank = ranks.get(str(result.get(provider_id, {}).get("confidence") or "").lower(), -1)
            if incoming_rank >= current_rank:
                result[provider_id] = item
    return result


def _normalized_api_format(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if (
        normalized.startswith("openai_chat_completions")
        or normalized in {"openai_compatible_json_and_sse", "openai_compatible"}
    ):
        return "chat_completions"
    if normalized.startswith("anthropic_messages"):
        return "anthropic_messages"
    return normalized or "chat_completions"


def _connection_metadata(provider_id: str) -> dict:
    item = _connection_catalog().get(provider_id)
    if not item:
        return {
            "connection_catalogued": False,
            "endpoint_verified": False,
            "quick_setup": False,
            "setup_mode": "advanced_review_required",
        }
    confidence = str(item.get("confidence") or "").lower()
    auth = item.get("auth") if isinstance(item.get("auth"), dict) else {}
    additional_fields = [
        str(value).strip()
        for value in [*(auth.get("additional_fields") or []), *(item.get("additional_fields") or [])]
        if str(value).strip()
    ]
    required = [str(value).strip() for value in (item.get("required_fields") or [])]
    if not required:
        required = [str(value).strip() for value in (auth.get("fields") or []) if str(value).strip()]
        required.extend(value for value in additional_fields if value not in required)
    if not required and item.get("setup_mode") == "api_key_only":
        required = ["api_key", *additional_fields]
    raw_protocol = item.get("protocol")
    protocol = raw_protocol if isinstance(raw_protocol, dict) else {}
    api_format = _normalized_api_format(str(
        item.get("api_format") or protocol.get("format") or raw_protocol or ""
    ))
    base_url = str(item.get("base_url") or item.get("verified_base_url") or "").strip()
    status = str(item.get("status") or item.get("compatibility") or "supported").lower()
    auth_type = str(item.get("auth_type") or auth.get("type") or "")
    explicitly_simple = item.get("setup_mode") == "api_key_only"
    key_only = required == ["api_key"] or (
        explicitly_simple and len(required) <= 1 and not additional_fields
    )
    adapter_ready = api_format in {"chat_completions", "anthropic_messages"}
    auth_ready = (
        "bearer" in auth_type
        or auth_type in {"authorization_api_key_scheme", "clarifai_pat"}
        or (auth_type == "x_api_key" and api_format in {"chat_completions", "anthropic_messages"})
    )
    static_url = bool(base_url) and "{" not in base_url and "}" not in base_url
    supported = (
        "unsupported" not in status
        and "not_verified" not in status
        and "provider_adapter" not in status
        and item.get("setup_mode") != "unsupported"
    )
    quick_setup = bool(
        confidence == "high" and key_only and adapter_ready and auth_ready and static_url and supported
    )
    endpoint = str(
        item.get("endpoint")
        or item.get("chat_endpoint")
        or (item.get("messages_endpoint") if api_format == "anthropic_messages" else "")
        or ""
    ).strip()
    raw_models_endpoint = item.get("models_endpoint")
    models_endpoint = raw_models_endpoint
    if isinstance(raw_models_endpoint, str) and raw_models_endpoint.startswith("/") and base_url:
        models_endpoint = base_url.rstrip("/") + raw_models_endpoint
    return {
        "connection_catalogued": True,
        "connection_confidence": confidence,
        "endpoint_verified": confidence == "high",
        "quick_setup": quick_setup,
        "setup_mode": "api_key_only" if quick_setup else (
            str(item.get("setup_mode") or "advanced_configuration")
        ),
        "api": base_url,
        "endpoint": endpoint,
        "api_format": api_format,
        "auth_type": auth_type,
        "required_fields": required,
        "models_endpoint": models_endpoint,
        "docs_url": str(item.get("docs_url") or ""),
        "protocol": str(protocol.get("format") or raw_protocol or ""),
        "connection_notes": str(item.get("notes") or ""),
        "source_urls": [str(value) for value in (item.get("source_urls") or []) if value],
    }

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

# Correcoes verificadas por provider para casos em que o catalogo generico
# descreve a familia, mas a API concreta nao expoe a mesma capacidade.
PROVIDER_CAPABILITY_OVERRIDES = {
    ("cerebras", "gemma-4-31b"): {"supports_thinking": False},
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
    global _catalog, _catalog_loaded_at
    if _catalog is not None and time.monotonic() - _catalog_loaded_at < CACHE_TTL_SECONDS:
        return _catalog
    with _lock:
        if _catalog is not None and time.monotonic() - _catalog_loaded_at < CACHE_TTL_SECONDS:
            return _catalog
        fresh = _read_cache(allow_stale=False)
        if fresh:
            _catalog = fresh
            _catalog_loaded_at = time.monotonic()
            return fresh
        try:
            _catalog = _fetch_catalog()
        except Exception:
            _catalog = _read_cache(allow_stale=True)
        _catalog_loaded_at = time.monotonic()
        return _catalog


def refresh_catalog() -> dict:
    """Atualiza imediatamente o snapshot do models.dev."""
    global _catalog, _catalog_loaded_at
    with _lock:
        _catalog = _fetch_catalog()
        _catalog_loaded_at = time.monotonic()
        return _catalog


def catalog_updated_at() -> str | None:
    """Data ISO do snapshot local, quando disponivel."""
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(os.path.getmtime(CACHE_FILE), timezone.utc).isoformat()
    except OSError:
        return None


def list_catalog_providers(query: str = "") -> list[dict]:
    """Lista todo o catalogo mundial sem misturar providers com os configurados."""
    needle = str(query or "").strip().lower()
    result = []
    for provider_id, raw in get_catalog().items():
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or provider_id)
        models = raw.get("models") or {}
        model_search_parts: list[str] = []
        if isinstance(models, dict):
            for model_id, model_raw in models.items():
                if isinstance(model_raw, dict):
                    model_search_parts.extend((
                        str(model_id),
                        str(model_raw.get("name") or ""),
                        str(model_raw.get("family") or ""),
                    ))
                else:
                    model_search_parts.append(str(model_id))
        model_search_index = " ".join(model_search_parts).lower()
        if needle and needle not in f"{provider_id} {name} {model_search_index}".lower():
            continue
        defaults = CATALOG_PROVIDER_DEFAULTS.get(str(provider_id), {})
        connection = _connection_metadata(str(provider_id))
        npm_package = str(raw.get("npm") or "")
        api_format = str(connection.get("api_format") or defaults.get("api_format") or (
            "anthropic_messages" if "anthropic" in npm_package else "chat_completions"
        ))
        result.append({
            "id": str(provider_id),
            "name": name,
            "model_count": sum(
                1 for model in models.values()
                if isinstance(model, dict) and _catalog_model_is_chat_compatible(model)
            ) if isinstance(models, dict) else 0,
            # Permite busca global instantanea no frontend sem uma requisicao por tecla.
            "model_search_index": model_search_index,
            "doc": str(raw.get("doc") or ""),
            "env": [str(value) for value in (raw.get("env") or []) if value],
            "npm": str(raw.get("npm") or ""),
            "api": str(connection.get("api") or raw.get("api") or defaults.get("api") or ""),
            "api_format": api_format,
            **connection,
        })
    return sorted(result, key=lambda item: (item["name"].lower(), item["id"]))


def _normalize_catalog_model(model_id: str, raw: dict) -> dict:
    modalities = raw.get("modalities") or {}
    inputs = modalities.get("input") or []
    outputs = modalities.get("output") or []
    limits = raw.get("limit") or {}
    return {
        "id": str(model_id),
        "name": str(raw.get("name") or model_id),
        "family": str(raw.get("family") or ""),
        "context_length": int(limits.get("context") or 0),
        "output_length": int(limits.get("output") or 0),
        "supports_images": "image" in inputs,
        "supports_video": "video" in inputs,
        "supports_audio": "audio" in inputs,
        "supports_text_output": not outputs or "text" in outputs,
        "supports_pdf": "pdf" in inputs,
        "supports_thinking": bool(raw.get("reasoning")),
        "supports_tools": bool(raw.get("tool_call")),
        "release_date": str(raw.get("release_date") or ""),
        "last_updated": str(raw.get("last_updated") or ""),
        "cost": raw.get("cost") if isinstance(raw.get("cost"), dict) else {},
        "catalog_source": "models.dev",
    }


def _catalog_model_is_chat_compatible(raw: dict) -> bool:
    """Keep non-text generators, embeddings and rerankers out of the chat selector."""
    modalities = raw.get("modalities") if isinstance(raw.get("modalities"), dict) else {}
    outputs = modalities.get("output") or []
    if outputs and "text" not in outputs:
        return False
    family = str(raw.get("family") or "").lower()
    model_id = str(raw.get("id") or "").lower()
    blocked = ("embedding", "rerank", "moderation", "text-to-speech", "speech-to-text")
    return not any(value in family or value in model_id for value in blocked)


def list_catalog_models(provider_id: str, query: str = "") -> list[dict]:
    provider = get_catalog().get(str(provider_id))
    if not isinstance(provider, dict):
        return []
    needle = str(query or "").strip().lower()
    result = []
    for model_id, raw in (provider.get("models") or {}).items():
        if not isinstance(raw, dict):
            continue
        if not _catalog_model_is_chat_compatible({**raw, "id": str(model_id)}):
            continue
        model = _normalize_catalog_model(str(model_id), raw)
        if needle and needle not in f'{model["id"]} {model["name"]} {model["family"]}'.lower():
            continue
        result.append(model)
    return sorted(result, key=lambda item: (item["name"].lower(), item["id"]))


def resolve_catalog_provider_id(provider_id: str) -> str | None:
    """Encontra a fonte preferencial de um provider configurado."""
    catalog = get_catalog()
    for candidate in PROVIDER_CATALOG_IDS.get(provider_id, (provider_id,)):
        if candidate in catalog:
            return candidate
    return None


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


def canonical_model_name(provider_id: str, model_id: str, reported_name: str = "") -> str:
    """Corrige nomes descobertos que contradizem o proprio ID do modelo."""
    normalized_id = str(model_id or "").strip()
    reported = str(reported_name or "").strip()
    if provider_id != "antigravity" or not normalized_id.lower().startswith("gemini-"):
        return reported or normalized_id

    words = normalized_id.split("-")
    labels = {
        "gemini": "Gemini",
        "flash": "Flash",
        "lite": "Lite",
        "pro": "Pro",
        "thinking": "Thinking",
        "preview": "Preview",
        "experimental": "Experimental",
        "exp": "Experimental",
        "image": "Image",
        "computer": "Computer",
        "use": "Use",
        "extra": "Extra",
        "low": "Low",
        "high": "High",
    }
    return " ".join(labels.get(word.lower(), word) for word in words)


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
            model["name"] = canonical_model_name(
                provider_id,
                str(model.get("id", "")),
                str(model.get("name", "")),
            )
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
        model.update(PROVIDER_CAPABILITY_OVERRIDES.get(
            (provider_id.lower(), str(model.get("id", "")).lower()),
            {},
        ))
        result.append(model)
    return result
