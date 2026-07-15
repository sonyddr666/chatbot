import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.core.agent.policy import authorize_tool
from src.core.agent.runtime import AgentContext
from src.core.agent.schemas import ToolDefinition
from src.core.agent.tool_registry import available_tools
from src.tools.calculator import calculate
from src.tools.url_reader import read_url_content


class AdminAgentToolTests(unittest.TestCase):
    def test_calculator_is_bounded_and_does_not_execute_python(self):
        self.assertIn("16.0", calculate("sqrt(16) + 12"))
        with self.assertRaises(ValueError):
            calculate("__import__('os').system('whoami')")
        with self.assertRaises(ValueError):
            calculate("9 ** 999999")

    def test_private_urls_are_rejected_before_http(self):
        private_address = [(2, 1, 6, "", ("127.0.0.1", 80))]
        with patch("src.tools.url_reader.socket.getaddrinfo", return_value=private_address):
            with self.assertRaisesRegex(ValueError, "locais, privadas"):
                asyncio.run(read_url_content("http://localhost/private"))

    def test_admin_tools_are_not_declared_for_normal_user(self):
        context = AgentContext(
            user_id=9,
            session_id="s",
            request="teste",
            attachments=[],
            provider_config={"provider_id": "test", "model_id": "m", "base_url": "https://example.test"},
        )
        with (
            patch("src.core.agent.tool_registry.SkillRepo.list_for_user", return_value=[]),
            patch("src.core.agent.tool_registry.has_antigravity_image_model", return_value=False),
            patch("src.core.agent.tool_registry.is_active_admin", return_value=False),
        ):
            names = {tool.definition.name for tool in available_tools(context)}
        self.assertEqual(names, {"get_time"})

    def test_execution_policy_rechecks_admin_status(self):
        definition = ToolDefinition(
            name="workspace_grep",
            description="test",
            input_schema={"type": "object"},
            permission="admin:workspace_read",
        )
        with patch(
            "src.core.agent.policy.UserRepo.get",
            return_value=SimpleNamespace(is_active=True, registration_status="approved", is_admin=False),
        ):
            with self.assertRaises(PermissionError):
                authorize_tool(9, definition)


if __name__ == "__main__":
    unittest.main()
