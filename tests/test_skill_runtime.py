import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.core.skill_runtime import (
    build_search_query,
    build_runtime_context,
    requests_web_search,
    requests_search_clarification,
    requests_workspace_search,
    run_enabled_skill_context,
    runtime_skill_activity,
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
        self.assertTrue(should_run_web_search("pesquisa meme", skills))
        self.assertFalse(should_run_web_search("me explique meu perfil", skills))
        self.assertFalse(should_run_web_search("me explique o resultado da pesquisa", skills))
        self.assertFalse(should_run_web_search("pesquise novidades de IA", [{"name": "simple_search", "enabled": False}]))
        self.assertTrue(requests_web_search("pode pesquisar sobre Veryti"))
        self.assertFalse(requests_web_search("o que apareceu na pesquisa?"))

    def test_local_file_search_never_routes_to_the_web(self):
        message = "tenta procurar uma imagem dentro do seu sistema"

        self.assertTrue(requests_workspace_search(message))
        self.assertFalse(requests_web_search(message))
        self.assertFalse(requests_search_clarification(message))
        self.assertTrue(requests_web_search("procure uma imagem na internet"))
        self.assertTrue(requests_search_clarification("procure uma imagem"))

    def test_search_query_deduplicates_quotes_and_resolves_recent_reference(self):
        repeated = build_search_query(
            7,
            'entao pesquisa sobre “Veryti” “Verity”“Veryti”“Verity”',
            "u7:test",
        )
        self.assertEqual(repeated, '"Veryti" "Verity"')

        current = "pesquise o nome dessa merda entao porrrrrrrrrraaaaaaaaa"
        history = [
            SimpleNamespace(role="user", content="Hi my name is veryti"),
            SimpleNamespace(role="assistant", content="Veryti parece um nome."),
            SimpleNamespace(role="user", content="pesquisa sobre oq isso se refere essa frase"),
            SimpleNamespace(role="user", content=current),
        ]
        with patch("src.core.skill_runtime.ConversationRepo.get_history", return_value=history):
            resolved = build_search_query(7, current, "u7:test")
        self.assertEqual(resolved, "veryti")

    def test_runtime_context_formats_web_search_result(self):
        context = build_runtime_context("web_search", "Resultados mockados")
        self.assertIn("Resultado da skill web_search", context)
        self.assertIn("Resultados mockados", context)

    def test_perplexo_context_creates_visible_completed_activity_with_sources(self):
        context = build_runtime_context(
            "perplexo_search",
            "Odin e um deus nordico.[1](https://example.test/odin) "
            "[2](https://example.test/mitologia)",
        )

        activity = runtime_skill_activity(context)

        self.assertIsNotNone(activity)
        self.assertEqual(activity["name"], "perplexo_search")
        self.assertEqual(activity["status"], "completed")
        self.assertEqual(activity["source_count"], 2)
        self.assertIn("Pesquisa Perplexo concluida", activity["label"])
        self.assertIn("JA foi executada", context)

        searched = runtime_skill_activity(build_runtime_context(
            "perplexo_search",
            "Consulta executada: meme\n\n[Meme](https://example.test/meme)",
        ))
        self.assertEqual(searched["query"], "meme")


class SkillRuntimeAsyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_local_file_search_uses_workspace_without_calling_web(self):
        workspace_skill = {
            "name": "workspace_manager",
            "enabled": True,
            "requires_shell": False,
            "definition": {"permissions": {"workspace_read": True, "workspace_write": True, "shell": False}},
        }
        with (
            patch("src.core.skill_runtime.SkillRepo.list_for_user", return_value=[workspace_skill]),
            patch("src.core.skill_runtime.search_files", return_value=[SimpleNamespace(path="images/foto.png", size=42)]),
            patch("src.core.skill_runtime.web_search", new=AsyncMock()) as web,
            patch("src.core.skill_runtime.perplexo_search", new=AsyncMock()) as perplexo,
            patch("src.core.skill_runtime.SkillRunRepo.create"),
        ):
            context = await run_enabled_skill_context(
                7,
                "tenta procurar uma imagem dentro do seu sistema",
                session_id="u7:test",
            )

        self.assertIn("images/foto.png", context)
        self.assertIn("somente no Workspace privado", context)
        web.assert_not_awaited()
        perplexo.assert_not_awaited()

    async def test_ambiguous_find_request_asks_scope_without_searching(self):
        search_skill = {"name": "simple_search", "enabled": True, "requires_shell": False}
        with (
            patch("src.core.skill_runtime.SkillRepo.list_for_user", return_value=[search_skill]),
            patch("src.core.skill_runtime.web_search", new=AsyncMock()) as web,
        ):
            context = await run_enabled_skill_context(7, "procure uma imagem")

        self.assertIn("internet ou nos arquivos do Workspace", context)
        web.assert_not_awaited()

    async def test_two_word_search_still_executes_enabled_skill(self):
        with (
            patch(
                "src.core.skill_runtime.SkillRepo.list_for_user",
                return_value=[{"name": "simple_search", "enabled": True, "requires_shell": False}],
            ),
            patch(
                "src.core.skill_runtime.web_search",
                new=AsyncMock(return_value="[Meme](https://example.test/meme)"),
            ) as search,
            patch("src.core.skill_runtime.SkillRunRepo.create"),
        ):
            context = await run_enabled_skill_context(7, "pesquisa meme", session_id="u7:test")

        search.assert_awaited_once_with("meme", max_results=3)
        self.assertIn("Consulta executada: meme", context)

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
