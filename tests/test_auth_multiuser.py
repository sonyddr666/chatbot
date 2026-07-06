import os
import unittest
from pathlib import Path

from src.config import settings
from src.core.auth import create_access_token, decode_access_token, hash_password, verify_password
from src.db.models import init_db
from src.db.repository import ConversationRepo, SkillRepo, UserRepo


class AuthMultiuserTest(unittest.TestCase):
    def setUp(self):
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        self.db_path = Path("C:/tmp/chatbot_auth_multiuser_test.db")
        if self.db_path.exists():
            os.remove(self.db_path)
        settings.database_url = f"sqlite:///{self.db_path.as_posix()}"
        init_db()

    def tearDown(self):
        if self.db_path.exists():
            os.remove(self.db_path)

    def test_password_hash_verifies_only_correct_password(self):
        password_hash = hash_password("secret123")
        self.assertTrue(verify_password("secret123", password_hash))
        self.assertFalse(verify_password("wrong", password_hash))

    def test_token_roundtrip_contains_user_identity(self):
        token = create_access_token(7, "ana")
        payload = decode_access_token(token)
        self.assertEqual(payload["sub"], "7")
        self.assertEqual(payload["username"], "ana")

    def test_conversations_are_filtered_by_user_id(self):
        user_a = UserRepo.create_user("a@example.test", "ana", "secret123", "Ana")
        user_b = UserRepo.create_user("b@example.test", "bia", "secret123", "Bia")

        ConversationRepo.add_message("u1:default", "user", "msg ana", user_id=user_a.id)
        ConversationRepo.add_message("u2:default", "user", "msg bia", user_id=user_b.id)

        convs_a = ConversationRepo.list_all(user_a.id)
        convs_b = ConversationRepo.list_all(user_b.id)

        self.assertEqual(len(convs_a), 1)
        self.assertEqual(len(convs_b), 1)
        self.assertEqual(convs_a[0].session_id, "u1:default")
        self.assertEqual(convs_b[0].session_id, "u2:default")

    def test_default_skills_can_be_enabled_per_user(self):
        user = UserRepo.create_user("skill@example.test", "skilluser", "secret123", "Skill")
        SkillRepo.ensure_defaults()

        before = SkillRepo.list_for_user(user.id)
        self.assertTrue(any(skill["name"] == "personal_rag" for skill in before))
        self.assertFalse(next(skill for skill in before if skill["name"] == "personal_rag")["enabled"])

        self.assertTrue(SkillRepo.set_enabled(user.id, "personal_rag", True))
        after = SkillRepo.list_for_user(user.id)
        self.assertTrue(next(skill for skill in after if skill["name"] == "personal_rag")["enabled"])


if __name__ == "__main__":
    unittest.main()
