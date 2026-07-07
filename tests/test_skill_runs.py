import asyncio
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.config import settings
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
        self.assertEqual(runs[0]["skill_name"], "web_search")
        self.assertEqual(runs[0]["status"], "completed")
        self.assertIn("pesquise python", runs[0]["input_json"])
        self.assertIn("Fonte A", runs[0]["output_summary"])


if __name__ == "__main__":
    unittest.main()
