import os
import unittest
import uuid
from pathlib import Path

from src.config import settings
from src.core.auth import create_access_token
from src.db.models import init_db
from src.db.repository import UserRepo


class AuthRequiredTest(unittest.TestCase):
    def setUp(self):
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        self.db_path = Path(f"C:/tmp/chatbot_auth_required_{uuid.uuid4().hex}.db")
        settings.database_url = f"sqlite:///{self.db_path.as_posix()}"
        init_db()

    def tearDown(self):
        pass

    def test_resolve_authorized_user_requires_valid_bearer_token(self):
        from src.core.auth_required import resolve_authorized_user

        user = UserRepo.create_user("required@example.test", "required", "secret123", "Required")
        token = create_access_token(user.id, user.username)

        self.assertIsNone(resolve_authorized_user(None))
        self.assertIsNone(resolve_authorized_user(""))
        self.assertIsNone(resolve_authorized_user("Bearer invalid-token"))

        resolved = resolve_authorized_user(f"Bearer {token}")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, user.id)


if __name__ == "__main__":
    unittest.main()
