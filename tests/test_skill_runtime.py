import unittest

from src.core.skill_runtime import (
    build_runtime_context,
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


if __name__ == "__main__":
    unittest.main()
