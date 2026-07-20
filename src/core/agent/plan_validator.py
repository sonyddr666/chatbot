"""Deterministic validation for model-proposed tool plans."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter

from src.core.agent.schemas import ToolCall, ToolDefinition
from src.core.classifier import IMAGE_TOOLS, SEARCH_TOOLS, ToolRoute


TOOL_CATEGORIES = {
    **{name: "search" for name in SEARCH_TOOLS},
    "conversation_history": "history",
    "workspace_search": "workspace_search",
    "workspace_grep": "workspace_search",
    "workspace_list": "workspace_list",
    "workspace_read": "workspace_read",
    "file_delivery": "file_delivery",
    "get_time": "time",
    "get_weather": "weather",
    "read_url_content": "url",
    "calculate": "calculation",
    "rag_search": "rag",
    "schedule_task": "schedule",
    "list_schedules": "schedule",
    "cancel_schedule": "schedule",
    "image_generate": "image",
    "image_edit": "image",
}

DEFAULT_BUDGETS = {
    "search": 1,
    "history": 1,
    "workspace_search": 1,
    "workspace_list": 1,
    "workspace_read": 2,
    "file_delivery": 1,
    "time": 1,
    "weather": 1,
    "url": 1,
    "calculation": 1,
    "rag": 1,
    "schedule": 1,
    "image": 1,
}


def tool_category(name: str) -> str:
    return TOOL_CATEGORIES.get(name, name)


_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
}


def _arguments_error(arguments: dict, schema: dict) -> str:
    """Lightweight check of required keys, primitive types and enums.

    Deliberately not a full JSON-Schema implementation: it catches the common
    planner mistakes (missing/empty required keys, wrong primitive type, value
    outside a declared enum) without adding a dependency.
    """
    if not isinstance(schema, dict):
        return ""
    properties = schema.get("properties") or {}
    for key in schema.get("required") or []:
        value = arguments.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return f"missing required: {key}"
    for key, spec in properties.items():
        if key not in arguments or not isinstance(spec, dict):
            continue
        value = arguments[key]
        check = _TYPE_CHECKS.get(spec.get("type"))
        if check is not None and not check(value):
            return f"invalid type: {key}"
        enum = spec.get("enum")
        if enum and value not in enum:
            return f"invalid enum: {key}"
    return ""


def _normalized_arguments(call: ToolCall) -> str:
    raw = json.dumps(call.arguments, ensure_ascii=False, sort_keys=True)
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(char for char in raw if not unicodedata.combining(char)).lower()
    return re.sub(r"\W+", " ", raw).strip()


def validate_tool_calls(
    calls: list[ToolCall],
    route: ToolRoute,
    used_counts: Counter | None = None,
    seen: set[str] | None = None,
    definitions: dict[str, ToolDefinition] | None = None,
    rejected: list[dict] | None = None,
) -> list[ToolCall]:
    """Filter unauthorized intent, duplicate calls and exhausted categories.

    ``definitions`` maps tool name to its declaration; when provided, category
    and terminal metadata come from the declaration instead of the legacy
    name-based tables. ``rejected``, when provided, is filled with
    {"id", "name", "reason"} dicts describing every discarded call.
    """
    counts = used_counts if used_counts is not None else Counter()
    signatures = seen if seen is not None else set()
    accepted: list[ToolCall] = []
    accepted_categories = Counter()

    def _definition(name: str) -> ToolDefinition | None:
        return definitions.get(name) if definitions else None

    def _category(call: ToolCall) -> str:
        definition = _definition(call.name)
        if definition is not None and definition.category:
            return definition.category
        return tool_category(call.name)

    def _terminal(call: ToolCall) -> bool:
        definition = _definition(call.name)
        if definition is not None:
            return definition.terminal
        return _category(call) == "image"

    def _reject(call: ToolCall, reason: str) -> None:
        if rejected is not None:
            rejected.append({"id": call.id, "name": call.name, "reason": reason})

    for call in calls:
        if call.name not in route.allowed_tools:
            _reject(call, "not_in_route")
            continue
        definition = _definition(call.name)
        if definition is not None and definition.input_schema:
            argument_error = _arguments_error(call.arguments, definition.input_schema)
            if argument_error:
                _reject(call, f"invalid_arguments:{argument_error}")
                continue
        category = _category(call)
        if (
            call.name in IMAGE_TOOLS or category == "image"
        ) and route.action_confidences.get("image") == "low":
            _reject(call, "low_confidence")
            continue
        budget = DEFAULT_BUDGETS.get(category, 1)
        if counts[category] + accepted_categories[category] >= budget:
            _reject(call, "budget_exceeded")
            continue
        signature = f"{category}:{_normalized_arguments(call)}"
        if signature in signatures:
            _reject(call, "duplicate")
            continue
        signatures.add(signature)
        accepted.append(call)
        accepted_categories[category] += 1

    # A terminal action is always last. If other work is pending, runtime may defer it.
    accepted.sort(key=_terminal)
    return accepted
