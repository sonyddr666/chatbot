"""Provider/model capability contracts used by both the wire adapter and UI.

OpenAI-compatible describes the HTTP envelope, not the optional parameters
accepted by every provider.  This module keeps those optional contracts
explicit so an unknown gateway receives only the portable request fields.
"""

from __future__ import annotations

from urllib.parse import urlparse


REASONING_VALUES = {"auto", "none", "default", "low", "medium", "high", "xhigh", "max"}


def _identity(config: dict) -> tuple[str, str, str]:
    provider_id = str(config.get("provider_id") or "").strip().lower()
    model_id = str(config.get("model_id") or config.get("id") or "").strip().lower()
    hostname = (urlparse(str(config.get("base_url") or "")).hostname or "").lower()
    return provider_id, model_id, hostname


def reasoning_contract(config: dict) -> dict:
    """Return the validated reasoning control for one concrete model."""
    explicit = config.get("reasoning_efforts") or config.get("reasoning_options")
    if isinstance(explicit, (list, tuple)):
        values = [str(value).strip().lower() for value in explicit]
        values = list(dict.fromkeys(value for value in values if value in REASONING_VALUES and value != "auto"))
        if values:
            return {"control": "binary" if set(values) <= {"none", "default"} else "scale", "values": values}

    provider_id, model_id, hostname = _identity(config)
    style = str(config.get("reasoning_style") or "").strip().lower()
    supports_thinking = config.get("supports_thinking") is True

    if style in {"none", "disabled", "off"} or config.get("supports_thinking") is False:
        return {"control": "automatic", "values": []}

    if provider_id == "groq" or hostname == "api.groq.com":
        if "qwen3" in model_id:
            return {"control": "binary", "values": ["none", "default"]}
        if "gpt-oss" in model_id:
            return {"control": "scale", "values": ["low", "medium", "high"]}
        return {"control": "automatic", "values": []}

    if "morphllm.com" in hostname or provider_id == "morph":
        return {"control": "scale", "values": ["low", "medium", "high"]}
    if "openrouter.ai" in hostname or provider_id == "openrouter":
        return {"control": "scale", "values": ["low", "medium", "high"]}
    if provider_id == "codex-chatgpt":
        return {"control": "scale", "values": ["low", "medium", "high", "xhigh", "max"]}
    if provider_id == "openai" or hostname == "api.openai.com":
        return {"control": "scale", "values": ["low", "medium", "high", "xhigh"]}

    # A provider-level reasoning_style imported by a user is not enough to
    # prove which enum a particular model accepts. Unknown contracts omit it.
    if supports_thinking:
        return {"control": "automatic", "values": []}
    return {"control": "automatic", "values": []}


def adapt_reasoning_effort(config: dict, requested: str | None) -> str | None:
    contract = reasoning_contract(config)
    values = contract["values"]
    candidate = str(requested or "auto").strip().lower()
    if candidate == "auto" or not values:
        return None
    if candidate in values:
        return candidate
    if set(values) == {"none", "default"}:
        return "none" if candidate in {"off", "none"} else "default"
    if candidate in {"xhigh", "max"} and "high" in values:
        return "high"
    if candidate == "default":
        return None
    return "medium" if "medium" in values else values[0]


def with_reasoning_capabilities(config: dict) -> dict:
    enriched = dict(config)
    contract = reasoning_contract(enriched)
    enriched["reasoning_control"] = contract["control"]
    enriched["reasoning_efforts"] = contract["values"]
    return enriched
