"""Central, provider-neutral tool loop for durable chat jobs."""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from dataclasses import replace
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import uuid4

from src.core.agent.planner import decide_tool_calls
from src.core.agent.plan_validator import tool_category, validate_tool_calls
from src.core.agent.policy import authorize_tool
from src.core.agent.schemas import ToolCall, ToolResult
from src.core.agent.tool_registry import available_tools
from src.core.classifier import classify_tool_route


MAX_AGENT_STEPS = 2
DEFAULT_TOOL_TIMEOUT_SECONDS = 60
# Limites de contexto: o modelo final recebe resultados completos o bastante
# para sintetizar; o planner precisa apenas de um resumo do que ja foi feito.
MODEL_CONTEXT_MAX_CHARS = 4000
PLANNER_PRIOR_RESULT_MAX_CHARS = 1500


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
    recent_history: list[dict[str, str]] = field(default_factory=list)
    job_id: str = ""
    current_call_id: str = ""
    max_steps: int = MAX_AGENT_STEPS
    planner_config: dict[str, Any] | None = None
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
    route: Any | None = None
    visual_validation_performed: bool = False
    steps_exhausted: bool = False
    steps_used: int = 0
    planner_calls: int = 0
    tool_latencies: dict[str, float] = field(default_factory=dict)
    tool_timeouts: int = 0
    tool_rejected: int = 0

    @property
    def executed(self) -> bool:
        return bool(self.results)

    def model_context(self) -> str:
        if not self.results:
            return ""
        payload = [result.model_payload(max_chars=MODEL_CONTEXT_MAX_CHARS) for result in self.results]
        context = (
            "Ferramentas executadas pelo agent runtime para o pedido atual:\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            + "\nAs acoes acima ja terminaram. Responda ao pedido confirmando apenas o resultado real; "
            "nao diga que nao possui essas capacidades e nao invente outros resultados."
        )
        if self.steps_exhausted:
            context += (
                "\nO limite de etapas do agent runtime foi atingido; se faltou alguma acao planejada, "
                "informe ao usuario o que foi concluido e o que ficou pendente."
            )
        return context


async def run_agent_tools(context: AgentContext) -> AgentRunOutcome:
    if not provider_can_plan(context.provider_config):
        return AgentRunOutcome()
    route = classify_tool_route(context.request, context.attachments)
    if not route.allowed_tools:
        return AgentRunOutcome()
    registered = [
        tool for tool in available_tools(context)
        if tool.definition.name in route.allowed_tools
    ]
    outcome = AgentRunOutcome(tools_declared=[tool.definition.name for tool in registered], route=route)
    if not registered:
        return outcome
    if context.event_sink:
        await context.event_sink("tools.declared", {
            "tools": outcome.tools_declared,
        })
    definitions = [tool.definition for tool in registered]
    by_name = {tool.definition.name: tool for tool in registered}
    definitions_by_name = {tool.definition.name: tool.definition for tool in registered}
    seen: set[str] = set()
    used_counts: Counter = Counter()

    async def execute_one(call) -> ToolResult:
        registered_tool = by_name[call.name]
        call_context = replace(context, current_call_id=call.id)
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
            started_at = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    registered_tool.handler(call_context, call.arguments),
                    timeout=registered_tool.definition.timeout_seconds or DEFAULT_TOOL_TIMEOUT_SECONDS,
                )
            finally:
                outcome.tool_latencies[call.name] = round(time.monotonic() - started_at, 3)
        except asyncio.TimeoutError:
            outcome.tool_timeouts += 1
            result = ToolResult(
                call_id=call.id,
                name=call.name,
                status="failed",
                content="A ferramenta excedeu o tempo limite e foi interrompida.",
                error=f"timeout apos {registered_tool.definition.timeout_seconds}s",
                activity={
                    "name": call.name,
                    "status": "failed",
                    "label": f"Tempo limite excedido em {call.name}",
                    "source_count": 0,
                    "sources": [],
                },
            )
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
        if context.event_sink:
            await context.event_sink(
                "tool.completed" if result.status == "completed" else "tool.failed",
                result.model_payload(),
            )
        return result

    async def execute_batch(calls) -> list[ToolResult]:
        if not calls:
            return []
        parallel = []
        sequential = []
        for call in calls:
            definition = by_name[call.name].definition
            if (
                not definition.terminal
                and not definition.confirmation_required
                and definition.risk_level <= 1
            ):
                parallel.append(call)
            else:
                sequential.append(call)
        results = list(await asyncio.gather(*(execute_one(call) for call in parallel))) if parallel else []
        for call in sequential:
            results.append(await execute_one(call))
        for result in results:
            used_counts[tool_category(result.name)] += 1
        outcome.results.extend(results)
        return results

    # Atalho deterministico: uma unica ferramenta cujo schema declara
    # explicitamente "properties": {} nao tem argumento algum para o planner
    # extrair, entao a chamada semantica e desnecessaria. Ferramentas com
    # argumentos opcionais (ex.: get_time/timezone) ou com schema irrestrito
    # ({"type": "object"} sem properties) passam pelo planner normalmente:
    # e ele quem preenche os argumentos a partir do pedido.
    if len(definitions) == 1:
        properties = definitions[0].input_schema.get("properties")
        if isinstance(properties, dict) and not properties:
            direct_call = ToolCall(
                id=f"direct_{uuid4().hex}",
                name=definitions[0].name,
                arguments={},
            )
            pending = validate_tool_calls([direct_call], route, used_counts, seen)
            if pending:
                await execute_batch(pending)
            return outcome

    for step in range(context.max_steps):
        if context.event_sink:
            await context.event_sink("agent.planning", {
                "step": step + 1,
                "max_steps": context.max_steps,
                "has_prior_results": bool(outcome.results),
            })
        calls = await decide_tool_calls(
            request=context.request,
            attachment_summary=context.attachment_summary(),
            prior_results=[
                result.model_payload(max_chars=PLANNER_PRIOR_RESULT_MAX_CHARS)
                for result in outcome.results
            ],
            tools=definitions,
            provider_config=context.provider_config,
            planner_config=context.planner_config,
            recent_history=context.recent_history,
        )
        outcome.planner_calls += 1
        outcome.steps_used = step + 1
        rejected: list[dict] = []
        pending = validate_tool_calls(
            calls,
            route,
            used_counts,
            seen,
            definitions=definitions_by_name,
            rejected=rejected,
        )
        for item in rejected:
            outcome.tool_rejected += 1
            if context.event_sink:
                await context.event_sink("tool.rejected", item)
        if not pending:
            break
        terminal = [call for call in pending if by_name[call.name].definition.terminal]
        nonterminal = [call for call in pending if not by_name[call.name].definition.terminal]

        # Search/list must finish before path-dependent reads or a terminal image prompt.
        roots = [call for call in nonterminal if not by_name[call.name].definition.depends_on]
        dependents = [call for call in nonterminal if by_name[call.name].definition.depends_on]
        if roots and dependents:
            await execute_batch(roots)
        else:
            await execute_batch(nonterminal)

        # A simple terminal-only plan can execute immediately. Compound requests defer
        # image generation until supporting results have been collected.
        if terminal and not nonterminal and (step > 0 or not route.compound):
            await execute_batch(terminal[:1])
            break
        if terminal and nonterminal and step > 0 and not dependents:
            await execute_batch(terminal[:1])
            break

        if not route.compound:
            break
    else:
        # O loop esgotou os steps sem break: so e possivel em rota compound,
        # com trabalho executado na ultima etapa e plano possivelmente incompleto.
        if outcome.results:
            outcome.steps_exhausted = True
            if context.event_sink:
                await context.event_sink("agent.truncated", {
                    "max_steps": context.max_steps,
                    "executed_tools": [result.name for result in outcome.results],
                })
    return outcome
