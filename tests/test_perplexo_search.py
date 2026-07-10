import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from src.config import settings
from src.core.skill_runtime import run_enabled_skill_context
from src.tools.perplexo_search import perplexo_health, perplexo_search


class PerplexoClientTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.previous_key = settings.mcp_api_key
        settings.mcp_api_key = "test-only-key"

    def tearDown(self):
        settings.mcp_api_key = self.previous_key

    async def test_search_sends_authenticated_user_scoped_request_and_formats_sources(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["X-API-Key"], "test-only-key")
            payload = json.loads(request.content)
            self.assertEqual(payload["query"], "pesquise energia solar")
            self.assertEqual(payload["user_id"], "42")
            self.assertEqual(payload["focus"], "web")
            return httpx.Response(
                200,
                json={
                    "answer": "Energia solar cresceu.",
                    "citations": [{"title": "Fonte A", "url": "https://example.test/a"}],
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://perplexo.example.test",
        ) as client:
            result = await perplexo_search("pesquise energia solar", 42, client=client)

        self.assertIn("Energia solar cresceu", result)
        self.assertIn("[Fonte A](https://example.test/a)", result)

    async def test_health_uses_the_same_authenticated_service(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/health")
            self.assertEqual(request.headers["X-API-Key"], "test-only-key")
            return httpx.Response(200, json={"status": "healthy"})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://perplexo.example.test",
        ) as client:
            result = await perplexo_health(client)

        self.assertTrue(result["online"])
        self.assertEqual(result["service"]["status"], "healthy")


class PerplexoRuntimeTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _skill(config=None):
        return {
            "name": "perplexo_search",
            "enabled": True,
            "requires_shell": False,
            "requires_network": True,
            "definition": {
                "executor": "perplexo_search",
                "permissions": {"network": True, "shell": False},
            },
            "config": config or {},
        }

    async def test_deep_research_intent_selects_deep_academic_mode(self):
        with (
            patch("src.core.skill_runtime.SkillRepo.list_for_user", return_value=[self._skill()]),
            patch(
                "src.core.skill_runtime.perplexo_search",
                new=AsyncMock(return_value="Resposta profunda com fontes"),
            ) as search,
            patch("src.core.skill_runtime.SkillRunRepo.create") as create_run,
        ):
            context = await run_enabled_skill_context(
                7,
                "faca uma pesquisa profunda sobre agentes autonomos",
            )

        self.assertIn("Resposta profunda", context)
        self.assertEqual(search.call_args.kwargs["model"], "deep-research")
        self.assertEqual(search.call_args.kwargs["focus"], "academic")
        self.assertEqual(create_run.call_args.args[1], "perplexo_search")
        self.assertEqual(create_run.call_args.args[2], "completed")

    async def test_offline_perplexo_falls_back_without_breaking_chat(self):
        with (
            patch("src.core.skill_runtime.SkillRepo.list_for_user", return_value=[self._skill()]),
            patch(
                "src.core.skill_runtime.perplexo_search",
                new=AsyncMock(side_effect=RuntimeError("offline")),
            ),
            patch(
                "src.core.skill_runtime.web_search",
                new=AsyncMock(return_value="Resultado do fallback"),
            ),
            patch("src.core.skill_runtime.SkillRunRepo.create") as create_run,
        ):
            context = await run_enabled_skill_context(8, "pesquise noticias de IA")

        self.assertIn("Resultado do fallback", context)
        self.assertEqual(create_run.call_args.args[2], "completed")
        self.assertEqual(create_run.call_args.args[3]["fallback"], "web_search")


if __name__ == "__main__":
    unittest.main()
