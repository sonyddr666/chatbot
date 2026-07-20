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

    async def test_planner_receives_filtered_recent_conversation_context(self):
        tool = ToolDefinition(name="image_generate", description="gera imagem", input_schema={"type": "object"})
        native = AsyncMock(return_value=[])
        history = [
            {"role": "user", "content": "Vamos falar sobre cidades sustentaveis."},
            {"role": "assistant", "content": "Falamos sobre jardins verticais e transporte limpo."},
        ]
        with patch("src.core.agent.planner._native_openai_decision", new=native):
            await decide_tool_calls(
                request="crie uma imagem baseada na nossa conversa",
                attachment_summary=[],
                prior_results=[],
                tools=[tool],
                provider_config={"provider_id": "test", "model_id": "m", "base_url": "https://example.test"},
                recent_history=history,
            )
        request_payload = native.await_args.args[0]
        self.assertEqual(request_payload["recent_conversation_context"], history)

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
        ambiguous = classify_tool_route("gera alguma coisa pra mim")
        textual = classify_tool_route("gera uma duvida pra mim")
        compound = classify_tool_route("gere uma imagem pesquisando codex e lendo arquivos e historico")
        self.assertEqual(simple.allowed_tools, frozenset({"image_generate"}))
        self.assertEqual(simple.confidence, "high")
        self.assertEqual(ambiguous.confidence, "medium")
        self.assertTrue(ambiguous.requires_visual_validation)
        self.assertEqual(textual.confidence, "low")
        self.assertNotIn("image_generate", textual.allowed_tools)
        self.assertFalse(simple.compound)
        self.assertTrue(compound.compound)
        self.assertTrue(compound.requires_final_synthesis)
        self.assertIn("image_generate", compound.allowed_tools)
        self.assertIn("web_search", compound.allowed_tools)
        self.assertIn("conversation_history", compound.allowed_tools)
        self.assertIn("workspace_search", compound.allowed_tools)

        sequential = classify_tool_route(
            "Pensa a respeito de toda a nossa conversa e gera um texto para gerar uma imagem do texto que voce criar"
        )
        self.assertIn("image_generate", sequential.allowed_tools)
        self.assertTrue(sequential.requires_planning)
        self.assertTrue(sequential.uses_current_context)
        self.assertTrue(sequential.requires_final_synthesis)

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


class AgentHarnessImprovementsTests(unittest.IsolatedAsyncioTestCase):
    def _context(self, **overrides):
        base = dict(
            user_id=1,
            session_id="s",
            request="teste",
            attachments=[],
            provider_config={"provider_id": "test", "model_id": "m", "base_url": "https://example.test"},
        )
        base.update(overrides)
        return AgentContext(**base)

    def _route(self, *names, compound=False):
        return ToolRoute(allowed_tools=frozenset(names), compound=compound)

    def _registered(self, name, handler, **definition_kwargs):
        return RegisteredTool(
            definition=ToolDefinition(
                name=name,
                description=name,
                input_schema={"type": "object"},
                **definition_kwargs,
            ),
            handler=handler,
        )

    async def test_tool_timeout_fails_without_killing_the_batch(self):
        async def slow_handler(context, arguments):
            await asyncio.sleep(5)
            return ToolResult(call_id="c", name="noop", status="completed", content="tarde")

        registered = self._registered("noop", slow_handler, timeout_seconds=0.05)
        calls = [ToolCall(id="1", name="noop", arguments={})]
        with (
            patch("src.core.agent.runtime.available_tools", return_value=[registered]),
            patch("src.core.agent.runtime.decide_tool_calls", new=AsyncMock(side_effect=[calls, []])),
            patch("src.core.agent.runtime.classify_tool_route", return_value=self._route("noop")),
        ):
            outcome = await run_agent_tools(self._context())
        self.assertEqual(outcome.results[0].status, "failed")
        self.assertIn("timeout", outcome.results[0].error)
        self.assertEqual(outcome.tool_timeouts, 1)
        self.assertIn("noop", outcome.tool_latencies)

    async def test_single_tool_without_properties_skips_planner(self):
        async def handler(context, arguments):
            return ToolResult(call_id=context.current_call_id, name="noop", status="completed", content="ok")

        registered = RegisteredTool(
            definition=ToolDefinition(
                name="noop",
                description="noop",
                input_schema={"type": "object", "properties": {}, "required": []},
            ),
            handler=handler,
        )
        decide = AsyncMock(return_value=[])
        with (
            patch("src.core.agent.runtime.available_tools", return_value=[registered]),
            patch("src.core.agent.runtime.decide_tool_calls", new=decide),
            patch("src.core.agent.runtime.classify_tool_route", return_value=self._route("noop")),
        ):
            outcome = await run_agent_tools(self._context())
        self.assertTrue(outcome.executed)
        self.assertEqual(outcome.planner_calls, 0)
        decide.assert_not_awaited()

    async def test_tool_with_optional_arguments_still_uses_planner(self):
        async def handler(context, arguments):
            return ToolResult(call_id="c", name="noop", status="completed", content="ok")

        registered = RegisteredTool(
            definition=ToolDefinition(
                name="noop",
                description="noop",
                input_schema={
                    "type": "object",
                    "properties": {"optional": {"type": "string"}},
                    "required": [],
                },
            ),
            handler=handler,
        )
        decide = AsyncMock(side_effect=[[ToolCall(id="1", name="noop", arguments={"optional": "x"})], []])
        with (
            patch("src.core.agent.runtime.available_tools", return_value=[registered]),
            patch("src.core.agent.runtime.decide_tool_calls", new=decide),
            patch("src.core.agent.runtime.classify_tool_route", return_value=self._route("noop")),
        ):
            outcome = await run_agent_tools(self._context())
        decide.assert_awaited()
        self.assertTrue(outcome.executed)

    async def test_rejected_calls_emit_event_and_count(self):
        events = []

        async def sink(name, payload):
            events.append((name, payload))

        registered = self._registered("noop", AsyncMock())
        calls = [ToolCall(id="1", name="other_tool", arguments={})]
        with (
            patch("src.core.agent.runtime.available_tools", return_value=[registered]),
            patch("src.core.agent.runtime.decide_tool_calls", new=AsyncMock(side_effect=[calls, []])),
            patch("src.core.agent.runtime.classify_tool_route", return_value=self._route("noop", "other_tool")),
        ):
            outcome = await run_agent_tools(self._context(event_sink=sink))
        rejected = [payload for name, payload in events if name == "tool.rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["reason"], "not_in_route")
        self.assertEqual(outcome.tool_rejected, 1)

    async def test_compound_route_exhausting_steps_marks_truncated(self):
        events = []

        async def sink(name, payload):
            events.append((name, payload))

        async def handler(context, arguments):
            return ToolResult(call_id=context.current_call_id, name="noop", status="completed", content="ok")

        # category com orcamento 2 para as duas chamadas serem aceitas e o loop esgotar
        registered = self._registered("noop", handler, category="workspace_read")
        decisions = [
            [ToolCall(id="1", name="noop", arguments={"value": 1})],
            [ToolCall(id="2", name="noop", arguments={"value": 2})],
        ]
        with (
            patch("src.core.agent.runtime.available_tools", return_value=[registered]),
            patch("src.core.agent.runtime.decide_tool_calls", new=AsyncMock(side_effect=decisions)),
            patch("src.core.agent.runtime.classify_tool_route", return_value=self._route("noop", compound=True)),
        ):
            outcome = await run_agent_tools(self._context(event_sink=sink))
        self.assertTrue(outcome.steps_exhausted)
        self.assertIn("limite de etapas", outcome.model_context())
        self.assertIn("agent.truncated", [name for name, _ in events])
        self.assertEqual(outcome.steps_used, 2)

    def test_model_payload_truncates_only_with_max_chars(self):
        result = ToolResult(call_id="c", name="t", status="completed", content="x" * 5000)
        self.assertEqual(len(result.model_payload()["content"]), 5000)
        truncated = result.model_payload(max_chars=100)
        self.assertTrue(truncated["content"].endswith("...[truncado]"))
        self.assertLess(len(truncated["content"]), 200)

    def test_validator_rejects_invalid_arguments_with_definitions(self):
        route = ToolRoute(allowed_tools=frozenset({"web_search"}))
        definitions = {
            "web_search": ToolDefinition(
                name="web_search",
                description="busca",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                category="search",
            )
        }
        rejected = []
        accepted = validate_tool_calls(
            [ToolCall(id="1", name="web_search", arguments={})],
            route,
            definitions=definitions,
            rejected=rejected,
        )
        self.assertEqual(accepted, [])
        self.assertTrue(rejected[0]["reason"].startswith("invalid_arguments"))

    def test_validator_uses_definition_category_over_name_table(self):
        route = ToolRoute(allowed_tools=frozenset({"custom_tool"}))
        definitions = {
            "custom_tool": ToolDefinition(
                name="custom_tool",
                description="custom",
                input_schema={"type": "object"},
                category="search",
            )
        }
        calls = [
            ToolCall(id="1", name="custom_tool", arguments={"q": "a"}),
            ToolCall(id="2", name="custom_tool", arguments={"q": "b"}),
        ]
        accepted = validate_tool_calls(calls, route, definitions=definitions)
        # category "search" tem orcamento 1, mesmo o nome nao estando na tabela legada
        self.assertEqual(len(accepted), 1)


class AgentRoutingBilingualTests(unittest.TestCase):
    def test_english_requests_enable_tools(self):
        self.assertIn("get_time", classify_tool_route("what time is it now?").allowed_tools)
        self.assertIn("web_search", classify_tool_route("search the web for codex").allowed_tools)
        self.assertIn("get_weather", classify_tool_route("what is the weather in Paris?").allowed_tools)
        self.assertIn("workspace_search", classify_tool_route("find notes inside my workspace").allowed_tools)

    def test_portuguese_requests_still_enable_tools(self):
        self.assertIn("get_time", classify_tool_route("que horas sao?").allowed_tools)
        self.assertIn("get_weather", classify_tool_route("como esta o clima em Paris?").allowed_tools)

    def test_calculation_false_positive_removed(self):
        self.assertNotIn("calculate", classify_tool_route("me conta uma piada").allowed_tools)
        self.assertIn("calculate", classify_tool_route("quanto e 18 * 4?").allowed_tools)

    def test_link_mention_without_action_is_not_url_read(self):
        self.assertNotIn("read_url_content", classify_tool_route("me manda o link depois").allowed_tools)
        self.assertIn("read_url_content", classify_tool_route("leia https://example.com/docs").allowed_tools)

    def test_intent_is_deterministic(self):
        route_a = classify_tool_route("pesquise o clima e a hora agora")
        route_b = classify_tool_route("pesquise a hora agora e o clima")
        self.assertEqual(route_a.intent, route_b.intent)


if __name__ == "__main__":
    unittest.main()
