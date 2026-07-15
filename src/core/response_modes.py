"""Response mode policies shared by HTTP, WebSocket and LLM providers."""

from typing import Literal


ResponseMode = Literal["normal", "thinking", "live"]
ReasoningEffort = Literal["auto", "none", "default", "low", "medium", "high", "xhigh", "max"]
VALID_RESPONSE_MODES = {"normal", "thinking", "live"}
VALID_REASONING_EFFORTS = {"auto", "none", "default", "low", "medium", "high", "xhigh", "max"}

CODEX_MODE_PROFILES: dict[ResponseMode, dict[str, str | int]] = {
    "normal": {
        "reasoning_effort": "low",
        "reasoning_summary": "auto",
    },
    "thinking": {
        "reasoning_effort": "high",
        "reasoning_summary": "detailed",
    },
    "live": {
        "reasoning_effort": "low",
        "reasoning_summary": "concise",
    },
}


def normalize_response_mode(
    value: str | None,
    *,
    legacy_use_thinking: bool | None = None,
    default: str = "normal",
) -> ResponseMode:
    """Resolve a mode while preserving compatibility with older clients."""
    candidate = str(value or "").strip().lower()
    if candidate in VALID_RESPONSE_MODES:
        return candidate  # type: ignore[return-value]
    if legacy_use_thinking is not None:
        return "thinking" if legacy_use_thinking else "normal"
    fallback = str(default or "normal").strip().lower()
    return fallback if fallback in VALID_RESPONSE_MODES else "normal"  # type: ignore[return-value]


def response_mode_status(mode: ResponseMode) -> str:
    if mode == "live":
        return "Modo Live: gerando resposta para voz..."
    if mode == "thinking":
        return "Modelo analisando em profundidade..."
    return "Modelo preparando a resposta..."


def normalize_reasoning_effort(
    value: str | None,
    *,
    mode: ResponseMode = "normal",
) -> ReasoningEffort:
    candidate = str(value or "").strip().lower()
    if candidate in VALID_REASONING_EFFORTS:
        return candidate  # type: ignore[return-value]
    return str(CODEX_MODE_PROFILES[mode]["reasoning_effort"])  # type: ignore[return-value]


def codex_wire_reasoning_effort(effort: ReasoningEffort) -> str:
    """OpenClaw-compatible maximum: the Codex wire ceiling is xhigh."""
    if effort in {"auto", "default"}:
        return "medium"
    if effort == "none":
        return "low"
    return "xhigh" if effort == "max" else effort
