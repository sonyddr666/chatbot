import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.app import app
from src.config import settings
from src.core.auth import create_access_token
from src.db.models import init_db
from src.db.repository import UserRepo


class PreferencesTest(unittest.TestCase):
    def setUp(self):
        self.previous_database_url = settings.database_url
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path(f"C:/tmp/chatbot_preferences_{uuid.uuid4().hex}.db")
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        init_db()
        self.user = UserRepo.create_user(
            f"prefs-{uuid.uuid4().hex[:8]}@example.test",
            f"prefs_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Prefs",
        )
        self.other = UserRepo.create_user(
            f"other-prefs-{uuid.uuid4().hex[:8]}@example.test",
            f"other_prefs_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Other Prefs",
        )

    def tearDown(self):
        settings.database_url = self.previous_database_url

    def test_preference_repo_stores_values_per_user(self):
        from src.db.repository import UserPreferenceRepo

        UserPreferenceRepo.set(self.user.id, "answer_style", {"tone": "direto"}, source="manual")
        UserPreferenceRepo.set(self.other.id, "answer_style", {"tone": "detalhado"}, source="manual")

        mine = UserPreferenceRepo.list_for_user(self.user.id)
        other = UserPreferenceRepo.list_for_user(self.other.id)

        self.assertEqual(mine["answer_style"]["value"], {"tone": "direto"})
        self.assertEqual(other["answer_style"]["value"], {"tone": "detalhado"})
        context = UserPreferenceRepo.prompt_context_for_user(self.user.id)
        self.assertIn("Preferencias pessoais do usuario", context)
        self.assertIn('"tone": "direto"', context)
        self.assertNotIn("detalhado", context)

    def test_preferences_endpoints_read_and_update_current_user(self):
        token = create_access_token(self.user.id, self.user.username)
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {token}"}

        put_response = client.put(
            "/api/v1/preferences/answer_style",
            headers=headers,
            json={"value": {"tone": "direto"}, "source": "manual", "confidence": 1.0},
        )
        get_response = client.get("/api/v1/preferences", headers=headers)

        self.assertEqual(put_response.status_code, 200)
        self.assertEqual(get_response.status_code, 200)
        data = get_response.json()
        self.assertEqual(data["preferences"]["answer_style"]["value"], {"tone": "direto"})
        self.assertEqual(data["preferences"]["answer_style"]["source"], "manual")


if __name__ == "__main__":
    unittest.main()
