import unittest
from unittest.mock import AsyncMock, patch

from src.core.skill_runtime import (
    build_runtime_context,
    run_enabled_skill_context,
    should_force_rag,
    should_run_web_search,
)


class SkillRuntimeTest(unittest.TestCase):
    def test_personal_rag_enabled_forces_rag(self):
        skills = [{"name": "personal_rag", "enabled": True}]
        self.assertTrue(should_force_rag(skills))

    def test_web_search_requires_enabled_search_skill_and_search_intent(self):
        skills = [{"name": "simple_search", "enabled": True}]
        self.assertTrue(should_run_web_search("pesquise novidades de IA", skills))
        self.assertFalse(should_run_web_search("me explique meu perfil", skills))
        self.assertFalse(should_run_web_search("pesquise novidades de IA", [{"name": "simple_search", "enabled": False}]))

    def test_runtime_context_formats_web_search_result(self):
        context = build_runtime_context("web_search", "Resultados mockados")
        self.assertIn("Resultado da skill web_search", context)
        self.assertIn("Resultados mockados", context)


class SkillRuntimeAsyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_web_search_failure_is_logged_without_breaking_chat_context(self):
        with (
            patch(
                "src.core.skill_runtime.SkillRepo.list_for_user",
                return_value=[{"name": "simple_search", "enabled": True, "requires_shell": False}],
            ),
            patch(
                "src.core.skill_runtime.web_search",
                new=AsyncMock(side_effect=RuntimeError("search offline")),
            ),
            patch("src.core.skill_runtime.SkillRunRepo.create") as create_run,
        ):
            context = await run_enabled_skill_context(7, "pesquise noticias de IA")

        self.assertEqual(context, "")
        create_run.assert_called_once()
        self.assertEqual(create_run.call_args.args[0], 7)
        self.assertEqual(create_run.call_args.args[1], "web_search")
        self.assertEqual(create_run.call_args.args[2], "failed")
        self.assertIn("search offline", create_run.call_args.kwargs["error_message"])


if __name__ == "__main__":
    unittest.main()
