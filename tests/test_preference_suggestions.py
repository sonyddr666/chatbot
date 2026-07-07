import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.app import app
from src.config import settings
from src.core.auth import create_access_token
from src.db.models import init_db
from src.db.repository import UserPreferenceRepo, UserRepo


class PreferenceSuggestionTest(unittest.TestCase):
    def setUp(self):
        self.previous_database_url = settings.database_url
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path(f"C:/tmp/chatbot_preference_suggestions_{uuid.uuid4().hex}.db")
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        init_db()
        self.user = UserRepo.create_user(
            f"suggestions-{uuid.uuid4().hex[:8]}@example.test",
            f"suggestions_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Suggestions",
        )
        self.other = UserRepo.create_user(
            f"other-suggestions-{uuid.uuid4().hex[:8]}@example.test",
            f"other_suggestions_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Other Suggestions",
        )

    def tearDown(self):
        settings.database_url = self.previous_database_url

    def test_explicit_preference_creates_one_pending_suggestion_and_blocks_secrets(self):
        from src.core.preference_suggestions import create_suggestion_from_message
        from src.db.repository import PreferenceSuggestionRepo

        suggestion = create_suggestion_from_message(
            self.user.id,
            "prefiro respostas bem detalhadas quando eu pedir explicacao",
        )
        duplicate = create_suggestion_from_message(
            self.user.id,
            "prefiro respostas bem detalhadas quando eu pedir explicacao de novo",
        )
        secret = create_suggestion_from_message(
            self.user.id,
            "minha senha eh abc123 e prefiro respostas detalhadas",
        )

        self.assertIsNotNone(suggestion)
        self.assertIsNone(duplicate)
        self.assertIsNone(secret)

        pending = PreferenceSuggestionRepo.list_pending(self.user.id)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["suggestion_type"], "answer_style")
        self.assertEqual(pending[0]["suggested_value"]["detail"], "detalhado")

    def test_accepting_suggestion_updates_current_user_preferences_only(self):
        from src.db.repository import PreferenceSuggestionRepo

        suggestion = PreferenceSuggestionRepo.create(
            self.user.id,
            "rag_aggressiveness",
            current_value="balanced",
            suggested_value="high",
            reason="Usuario pediu para usar documentos pessoais com mais frequencia.",
            confidence=0.8,
        )
        self.assertFalse(PreferenceSuggestionRepo.resolve(self.other.id, suggestion.id, accept=True))
        self.assertTrue(PreferenceSuggestionRepo.resolve(self.user.id, suggestion.id, accept=True))

        mine = UserPreferenceRepo.list_for_user(self.user.id)
        other = UserPreferenceRepo.list_for_user(self.other.id)

        self.assertEqual(mine["rag_aggressiveness"]["value"], "high")
        self.assertEqual(mine["rag_aggressiveness"]["source"], "suggestion")
        self.assertEqual(other["rag_aggressiveness"]["value"], "balanced")
        self.assertEqual(PreferenceSuggestionRepo.list_pending(self.user.id), [])

    def test_suggestion_endpoints_list_and_resolve_current_user_pending_items(self):
        from src.db.repository import PreferenceSuggestionRepo

        token = create_access_token(self.user.id, self.user.username)
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {token}"}
        suggestion = PreferenceSuggestionRepo.create(
            self.user.id,
            "default_language",
            current_value="pt",
            suggested_value="en",
            reason="Usuario pediu respostas em ingles.",
            confidence=0.7,
        )
        PreferenceSuggestionRepo.create(
            self.other.id,
            "default_language",
            current_value="pt",
            suggested_value="es",
            reason="Outro usuario pediu espanhol.",
            confidence=0.7,
        )

        list_response = client.get("/api/v1/preference-suggestions", headers=headers)
        resolve_response = client.post(
            f"/api/v1/preference-suggestions/{suggestion.id}/resolve",
            headers=headers,
            json={"accept": True},
        )

        self.assertEqual(list_response.status_code, 200)
        data = list_response.json()
        self.assertEqual(len(data["suggestions"]), 1)
        self.assertEqual(data["suggestions"][0]["id"], suggestion.id)
        self.assertEqual(resolve_response.status_code, 200)
        self.assertEqual(resolve_response.json()["status"], "accepted")
        self.assertEqual(UserPreferenceRepo.list_for_user(self.user.id)["default_language"]["value"], "en")

    def test_chat_observer_creates_pending_suggestion_without_requiring_llm_call(self):
        from src.api.routes import observe_preference_suggestion
        from src.db.repository import PreferenceSuggestionRepo

        observe_preference_suggestion(
            self.user.id,
            "prefiro respostas detalhadas para tutoriais",
        )

        pending = PreferenceSuggestionRepo.list_pending(self.user.id)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["suggestion_type"], "answer_style")


if __name__ == "__main__":
    unittest.main()
