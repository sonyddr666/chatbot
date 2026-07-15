"""Deterministic validation for model-proposed tool plans."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter

from src.core.agent.schemas import ToolCall
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
) -> list[ToolCall]:
    """Filter unauthorized intent, duplicate calls and exhausted categories."""
    counts = used_counts if used_counts is not None else Counter()
    signatures = seen if seen is not None else set()
    accepted: list[ToolCall] = []
    accepted_categories = Counter()

    for call in calls:
        if call.name not in route.allowed_tools:
            continue
        if call.name in IMAGE_TOOLS and route.action_confidences.get("image") == "low":
            continue
        category = tool_category(call.name)
        budget = DEFAULT_BUDGETS.get(category, 1)
        if counts[category] + accepted_categories[category] >= budget:
            continue
        signature = f"{category}:{_normalized_arguments(call)}"
        if signature in signatures:
            continue
        signatures.add(signature)
        accepted.append(call)
        accepted_categories[category] += 1

    # A terminal action is always last. If other work is pending, runtime may defer it.
    accepted.sort(key=lambda call: call.name in IMAGE_TOOLS)
    return accepted
