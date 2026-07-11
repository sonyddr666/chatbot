import os
import unittest
import uuid
from pathlib import Path

from src.config import settings
from src.db.models import init_db
from src.db.repository import SkillRepo, UserRepo


class SkillsContextTest(unittest.TestCase):
    def setUp(self):
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        self.db_path = Path(f"C:/tmp/chatbot_skills_context_{uuid.uuid4().hex}.db")
        settings.database_url = f"sqlite:///{self.db_path.as_posix()}"
        init_db()
        SkillRepo.ensure_defaults()

    def tearDown(self):
        pass

    def test_enabled_skills_become_prompt_context_for_the_user(self):
        user = UserRepo.create_user("skills-context@example.test", "skillctx", "secret123", "Skill Ctx")

        default_context = SkillRepo.enabled_context_for_user(user.id)
        self.assertIn("conversation_history", default_context)
        self.assertIn("outras conversas privadas", default_context)

        self.assertTrue(SkillRepo.set_enabled(user.id, "personal_rag", True))
        self.assertTrue(SkillRepo.set_enabled(user.id, "search_and_answer", False))

        context = SkillRepo.enabled_context_for_user(user.id)

        self.assertIn("Skills habilitadas para este usuario", context)
        self.assertIn("conversation_history", context)
        self.assertIn("personal_rag", context)
        self.assertIn("Consulta a base de conhecimento pessoal", context)
        self.assertNotIn("search_and_answer", context)


if __name__ == "__main__":
    unittest.main()
