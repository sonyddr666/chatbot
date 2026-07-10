import asyncio
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.api.app import app
from src.config import settings
from src.core.auth import create_access_token
from src.db.models import init_db
from src.db.repository import SkillRepo, UserRepo


class SkillRunsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_database_url = settings.database_url
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path(f"C:/tmp/chatbot_skill_runs_{uuid.uuid4().hex}.db")
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        init_db()
        self.user = UserRepo.create_user(
            f"skill-runs-{uuid.uuid4().hex[:8]}@example.test",
            f"skill_runs_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Skill Runs",
        )

    def tearDown(self):
        settings.database_url = self.previous_database_url

    def test_web_search_skill_execution_is_logged_for_user(self):
        from src.core.skill_runtime import run_enabled_skill_context
        from src.db.repository import SkillRunRepo

        SkillRepo.set_enabled(self.user.id, "simple_search", True)

        with patch("src.core.skill_runtime.web_search", new=AsyncMock(return_value="Fonte A")):
            context = asyncio.run(run_enabled_skill_context(self.user.id, "pesquise python"))

        runs = SkillRunRepo.list_for_user(self.user.id)
        self.assertIn("Fonte A", context)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["skill_name"], "simple_search")
        self.assertEqual(runs[0]["status"], "completed")
        self.assertIn("pesquise python", runs[0]["input_json"])
        self.assertIn("Fonte A", runs[0]["output_summary"])

    def test_personal_rag_forced_in_chat_is_logged_for_user(self):
        from src.db.repository import SkillRunRepo

        SkillRepo.set_enabled(self.user.id, "personal_rag", True)
        token = create_access_token(self.user.id, self.user.username)

        class FakeChatEngine:
            def __init__(self, memory, provider_config=None):
                pass

            async def chat(self, message):
                return "resposta"

        with (
            patch("src.api.routes.retrieve_user_context", return_value="contexto pessoal"),
            patch("src.api.routes.ChatEngine", new=FakeChatEngine),
        ):
            response = TestClient(app).post(
                "/api/v1/chat",
                headers={"Authorization": f"Bearer {token}"},
                json={"message": "use minha memoria", "session_id": "personal-rag-log", "use_rag": False},
            )

        runs = SkillRunRepo.list_for_user(self.user.id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(run["skill_name"] == "personal_rag" for run in runs))
        personal_rag_run = next(run for run in runs if run["skill_name"] == "personal_rag")
        self.assertEqual(personal_rag_run["status"], "completed")
        self.assertIn("use minha memoria", personal_rag_run["input_json"])

    def test_skill_runs_endpoint_returns_only_current_user_runs(self):
        from src.db.repository import SkillRunRepo

        other = UserRepo.create_user(
            f"other-skill-runs-{uuid.uuid4().hex[:8]}@example.test",
            f"other_skill_runs_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Other",
        )
        SkillRunRepo.create(self.user.id, "web_search", "completed", {"message": "meu"}, "saida minha")
        SkillRunRepo.create(other.id, "web_search", "completed", {"message": "outro"}, "saida outro")

        token = create_access_token(self.user.id, self.user.username)
        response = TestClient(app).get(
            "/api/v1/skills/runs",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["runs"]), 1)
        self.assertEqual(data["runs"][0]["user_id"], self.user.id)
        self.assertIn("saida minha", data["runs"][0]["output_summary"])


if __name__ == "__main__":
    unittest.main()
