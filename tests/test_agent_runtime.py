import asyncio
import unittest
from collections import Counter
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.core.agent.planner import decide_tool_calls, parse_tool_calls
from src.core.agent.plan_validator import validate_tool_calls
from src.core.agent.runtime import AgentContext, run_agent_tools
from src.core.agent.schemas import RegisteredTool, ToolCall, ToolDefinition, ToolResult
from src.core.classifier import ToolRoute, classify_tool_route
from src.tools.get_time import current_time


class AgentPlannerTests(unittest.IsolatedAsyncioTestCase):
    def test_parses_native_and_fallback_tool_calls(self):
        allowed = {"image_generate"}
        fallback = parse_tool_calls(
            '{"tool_calls":[{"name":"image_generate","arguments":{"prompt":"um pato"}}]}',
            allowed,
        )
        native = parse_tool_calls(
            '{"tool_calls":[{"id":"call_1","type":"function","function":'
            '{"name":"image_generate","arguments":"{\\"prompt\\":\\"um pato\\"}"}}]}',
            allowed,
        )
        self.assertEqual(fallback[0].arguments["prompt"], "um pato")
        self.assertEqual(native[0].id, "call_1")
        self.assertEqual(native[0].arguments["prompt"], "um pato")

    def test_unknown_tools_are_discarded(self):
        calls = parse_tool_calls(
            '{"tool_calls":[{"name":"shell","arguments":{"command":"rm"}}]}',
            {"image_generate"},
        )
        self.assertEqual(calls, [])

    async def test_semantic_json_fallback_is_provider_neutral(self):
        tool = ToolDefinition(
            name="image_generate",
            description="gera imagem",
            input_schema={"type": "object", "properties": {"prompt": {"type": "string"}}},
        )
        with (
            patch("src.core.agent.planner._native_openai_decision", new=AsyncMock(return_value=None)),
            patch(
                "src.core.agent.planner.generate",
                new=AsyncMock(return_value='{"tool_calls":[{"name":"image_generate","arguments":{"prompt":"pato"}}]}'),
            ),
        ):
            calls = await decide_tool_calls(
                request="gera um pato",
                attachment_summary=[],
                prior_results=[],
                tools=[tool],
                provider_config={"provider_id": "antigravity"},
            )
        self.assertEqual(calls[0].name, "image_generate")

    def test_get_time_uses_user_timezone_and_real_calendar(self):
        with patch(
            "src.tools.get_time.UserRepo.get_profile",
            return_value=SimpleNamespace(timezone="America/Sao_Paulo"),
        ):
            result = current_time(
                7,
                now_utc=datetime(2026, 7, 15, 2, 57, 0, tzinfo=timezone.utc),
            )
        self.assertEqual(result["date"], "2026-07-14")
        self.assertEqual(result["time"], "23:57:00")
        self.assertEqual(result["weekday"], "terca-feira")
        self.assertEqual(result["utc_offset"], "-03:00")


class AgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_loop_executes_declared_tool_and_returns_result_context(self):
        events = []

        async def sink(name, payload):
            events.append((name, payload))

        async def handler(context, arguments):
            return ToolResult(
                call_id=context.current_call_id,
                name="image_generate",
                status="completed",
                content=f"imagem criada: {arguments['prompt']}",
            )

        registered = RegisteredTool(
            definition=ToolDefinition(
                name="image_generate",
                description="gera imagem",
                input_schema={"type": "object"},
            ),
            handler=handler,
        )
        decisions = [[ToolCall(id="call_1", name="image_generate", arguments={"prompt": "pato"})]]
        with (
            patch("src.core.agent.runtime.available_tools", return_value=[registered]),
            patch("src.core.agent.runtime.decide_tool_calls", new=AsyncMock(side_effect=decisions)),
        ):
            outcome = await run_agent_tools(AgentContext(
                user_id=7,
                session_id="s1",
                request="gera uma imagem de um pato",
                attachments=[],
                provider_config={"provider_id": "test", "model_id": "test-model", "base_url": "https://example.test/v1"},
                event_sink=sink,
            ))

        self.assertTrue(outcome.executed)
        self.assertIn("imagem criada", outcome.model_context())
        self.assertEqual([item[0] for item in events], [
            "tools.declared", "agent.planning", "tool.requested", "tool.started", "tool.completed",
        ])

    async def test_duplicate_calls_cannot_loop_forever(self):
        calls = [ToolCall(id="call_1", name="noop", arguments={"value": 1})]
        handler = AsyncMock(return_value=ToolResult(
            call_id="call_1", name="noop", status="completed", content="ok"
        ))
        registered = RegisteredTool(
            definition=ToolDefinition(name="noop", description="noop", input_schema={"type": "object"}),
            handler=handler,
        )
        with (
            patch("src.core.agent.runtime.available_tools", return_value=[registered]),
            patch("src.core.agent.runtime.decide_tool_calls", new=AsyncMock(return_value=calls)),
            patch(
                "src.core.agent.runtime.classify_tool_route",
                return_value=ToolRoute(allowed_tools=frozenset({"noop"})),
            ),
        ):
            outcome = await run_agent_tools(AgentContext(
                user_id=1,
                session_id="s",
                request="teste",
                attachments=[],
                provider_config={"provider_id": "test", "model_id": "test-model", "base_url": "https://example.test/v1"},
            ))
        self.assertEqual(len(outcome.results), 1)
        handler.assert_awaited_once()

    async def test_independent_tools_execute_in_parallel(self):
        active = 0
        maximum_active = 0

        async def handler(context, arguments):
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0.02)
            active -= 1
            return ToolResult(
                call_id=context.current_call_id,
                name=arguments["result_name"],
                status="completed",
                content="ok",
            )

        registered = [
            RegisteredTool(
                definition=ToolDefinition(name=name, description=name, input_schema={"type": "object"}),
                handler=handler,
            )
            for name in ("web_search", "conversation_history")
        ]
        decisions = [[
            ToolCall(id="search", name="web_search", arguments={"query": "codex", "result_name": "web_search"}),
            ToolCall(id="history", name="conversation_history", arguments={"query": "codex", "result_name": "conversation_history"}),
        ], []]
        with (
            patch("src.core.agent.runtime.available_tools", return_value=registered),
            patch("src.core.agent.runtime.decide_tool_calls", new=AsyncMock(side_effect=decisions)),
        ):
            outcome = await run_agent_tools(AgentContext(
                user_id=1,
                session_id="s",
                request="pesquise codex e consulte meu historico",
                attachments=[],
                provider_config={"provider_id": "test", "model_id": "m", "base_url": "https://example.test"},
            ))
        self.assertEqual(len(outcome.results), 2)
        self.assertEqual(maximum_active, 2)


class AgentRoutingTests(unittest.TestCase):
    def test_router_skips_tools_for_plain_chat(self):
        self.assertEqual(classify_tool_route("explique o que e uma abelha").allowed_tools, frozenset())
        self.assertEqual(classify_tool_route("explique meu projeto").allowed_tools, frozenset())

    def test_router_distinguishes_web_and_local_search(self):
        web = classify_tool_route("pesquise codex na internet")
        local = classify_tool_route("procure uma imagem dentro do sistema")
        self.assertIn("web_search", web.allowed_tools)
        self.assertNotIn("web_search", local.allowed_tools)
        self.assertIn("workspace_search", local.allowed_tools)

    def test_router_distinguishes_simple_and_compound_image_requests(self):
        simple = classify_tool_route("gere uma imagem de um pato")
        compound = classify_tool_route("gere uma imagem pesquisando codex e lendo arquivos e historico")
        self.assertEqual(simple.allowed_tools, frozenset({"image_generate"}))
        self.assertFalse(simple.compound)
        self.assertTrue(compound.compound)
        self.assertIn("image_generate", compound.allowed_tools)
        self.assertIn("web_search", compound.allowed_tools)
        self.assertIn("conversation_history", compound.allowed_tools)
        self.assertIn("workspace_search", compound.allowed_tools)

    def test_validator_enforces_one_search_budget(self):
        route = ToolRoute(
            allowed_tools=frozenset({"web_search"}),
            requested_categories=frozenset({"search"}),
        )
        calls = [
            ToolCall(id="1", name="web_search", arguments={"query": "codex"}),
            ToolCall(id="2", name="web_search", arguments={"query": "Codex OpenAI"}),
        ]
        accepted = validate_tool_calls(calls, route, Counter(), set())
        self.assertEqual(len(accepted), 1)


if __name__ == "__main__":
    unittest.main()
