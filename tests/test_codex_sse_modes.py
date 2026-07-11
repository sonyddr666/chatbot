import unittest

from src.core.codex_client import parse_codex_sse_event
from src.core.response_modes import (
    CODEX_MODE_PROFILES,
    codex_wire_reasoning_effort,
    normalize_reasoning_effort,
    normalize_response_mode,
)


class CodexSseModeTests(unittest.TestCase):
    def test_parser_separates_reasoning_and_content(self):
        self.assertEqual(
            parse_codex_sse_event({
                "type": "response.reasoning_summary_text.delta",
                "delta": "Analisando o pedido",
            }),
            [("reasoning", "Analisando o pedido")],
        )
        self.assertEqual(
            parse_codex_sse_event({
                "type": "response.output_text.delta",
                "delta": "Resposta final",
            }),
            [("content", "Resposta final")],
        )

    def test_parser_ignores_tool_argument_deltas(self):
        self.assertEqual(
            parse_codex_sse_event({
                "type": "response.function_call_arguments.delta",
                "delta": '{"path":"arquivo.txt"}',
            }),
            [],
        )

    def test_modes_preserve_legacy_clients_and_live_latency_policy(self):
        self.assertEqual(normalize_response_mode(None, legacy_use_thinking=True), "thinking")
        self.assertEqual(normalize_response_mode(None, legacy_use_thinking=False), "normal")
        self.assertEqual(normalize_response_mode("live"), "live")
        self.assertEqual(CODEX_MODE_PROFILES["live"]["reasoning_effort"], "low")
        self.assertEqual(CODEX_MODE_PROFILES["thinking"]["reasoning_summary"], "detailed")
        self.assertEqual(normalize_reasoning_effort("max", mode="thinking"), "max")
        self.assertEqual(codex_wire_reasoning_effort("max"), "xhigh")


if __name__ == "__main__":
    unittest.main()
