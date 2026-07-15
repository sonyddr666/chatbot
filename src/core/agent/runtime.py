"""Central, provider-neutral tool loop for durable chat jobs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from src.core.agent.planner import decide_tool_calls
from src.core.agent.policy import authorize_tool
from src.core.agent.schemas import ToolResult
from src.core.agent.tool_registry import available_tools


MAX_AGENT_STEPS = 3


def provider_can_plan(provider_config: dict[str, Any]) -> bool:
    provider_id = str(provider_config.get("provider_id") or "").strip().lower()
    model_id = str(provider_config.get("model_id") or "").strip()
    if not model_id:
        return False
    if provider_id in {"antigravity", "codex-chatgpt"}:
        return True
    return bool(provider_config.get("base_url"))


def _event_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in arguments.items():
        if key in {"content", "data", "base64"} and isinstance(value, str):
            safe[key] = {"omitted": True, "length": len(value)}
        elif isinstance(value, str) and len(value) > 500:
            safe[key] = value[:500] + "..."
        else:
            safe[key] = value
    return safe


@dataclass
class AgentContext:
    user_id: int
    session_id: str
    request: str
    attachments: list[dict[str, Any]]
    provider_config: dict[str, Any]
    job_id: str = ""
    current_call_id: str = ""
    event_sink: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None

    @property
    def latest_image(self) -> dict[str, Any] | None:
        return next(
            (item for item in self.attachments if item.get("kind") == "image"),
            None,
        )

    def attachment_summary(self) -> list[dict[str, Any]]:
        return [
            {
                "id": item.get("id"),
                "filename": item.get("filename"),
                "kind": item.get("kind"),
                "content_type": item.get("content_type"),
                "relative_path": item.get("relative_path") or item.get("path"),
            }
            for item in self.attachments
        ]


@dataclass
class AgentRunOutcome:
    tools_declared: list[str] = field(default_factory=list)
    results: list[ToolResult] = field(default_factory=list)

    @property
    def executed(self) -> bool:
        return bool(self.results)

    def model_context(self) -> str:
        if not self.results:
            return ""
        payload = [result.model_payload() for result in self.results]
        return (
            "Ferramentas executadas pelo agent runtime para o pedido atual:\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            + "\nAs acoes acima ja terminaram. Responda ao pedido confirmando apenas o resultado real; "
            "nao diga que nao possui essas capacidades e nao invente outros resultados."
        )


async def run_agent_tools(context: AgentContext) -> AgentRunOutcome:
    if not provider_can_plan(context.provider_config):
        return AgentRunOutcome()
    registered = available_tools(context)
    outcome = AgentRunOutcome(tools_declared=[tool.definition.name for tool in registered])
    if not registered:
        return outcome
    if context.event_sink:
        await context.event_sink("tools.declared", {
            "tools": outcome.tools_declared,
        })
    definitions = [tool.definition for tool in registered]
    by_name = {tool.definition.name: tool for tool in registered}
    seen: set[str] = set()

    for _ in range(MAX_AGENT_STEPS):
        calls = await decide_tool_calls(
            request=context.request,
            attachment_summary=context.attachment_summary(),
            prior_results=[result.model_payload() for result in outcome.results],
            tools=definitions,
            provider_config=context.provider_config,
        )
        pending = []
        for call in calls:
            signature = json.dumps(
                {"name": call.name, "arguments": call.arguments},
                ensure_ascii=False,
                sort_keys=True,
            )
            if signature not in seen:
                seen.add(signature)
                pending.append(call)
        if not pending:
            break
        for call in pending:
            registered_tool = by_name.get(call.name)
            if not registered_tool:
                continue
            context.current_call_id = call.id
            if context.event_sink:
                await context.event_sink("tool.requested", {
                    "id": call.id,
                    "name": call.name,
                    "arguments": _event_arguments(call.arguments),
                })
                await context.event_sink("tool.started", {
                    "id": call.id,
                    "name": call.name,
                })
            try:
                authorize_tool(context.user_id, registered_tool.definition)
                result = await registered_tool.handler(context, call.arguments)
            except Exception as exc:
                result = ToolResult(
                    call_id=call.id,
                    name=call.name,
                    status="failed",
                    content="A ferramenta falhou e nao produziu resultado.",
                    error=str(exc),
                    activity={
                        "name": call.name,
                        "status": "failed",
                        "label": f"Falha em {call.name}",
                        "source_count": 0,
                        "sources": [],
                    },
                )
            outcome.results.append(result)
            if context.event_sink:
                await context.event_sink(
                    "tool.completed" if result.status == "completed" else "tool.failed",
                    result.model_payload(),
                )
    return outcome
