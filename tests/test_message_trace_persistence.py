import json
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.app import app
from src.config import settings
from src.core.auth import create_access_token
from src.db.models import init_db
from src.db.repository import ConversationRepo, UserRepo


class MessageTracePersistenceTest(unittest.TestCase):
    def setUp(self):
        self.previous_database_url = settings.database_url
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path(f"C:/tmp/chatbot_trace_{uuid.uuid4().hex}.db")
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        init_db()
        self.user = UserRepo.create_user(
            f"trace-{uuid.uuid4().hex[:8]}@example.test",
            f"trace_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Trace User",
        )

    def tearDown(self):
        settings.database_url = self.previous_database_url

    def test_conversation_restores_reasoning_and_skill_activities(self):
        scoped_session = f"u{self.user.id}:trace-session"
        activity = {
            "name": "perplexo_search",
            "status": "completed",
            "label": "Pesquisa Perplexo concluida",
            "source_count": 1,
            "sources": [{"label": "Fonte 1", "url": "https://example.test/source"}],
        }
        ConversationRepo.add_message(scoped_session, "user", "pesquise", user_id=self.user.id)
        ConversationRepo.add_message(
            scoped_session,
            "assistant",
            "resultado",
            user_id=self.user.id,
            reasoning="raciocinio completo",
            skill_activities=[activity],
        )

        token = create_access_token(self.user.id, self.user.username)
        response = TestClient(app).get(
            "/api/v1/conversations/trace-session",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        assistant = response.json()["messages"][-1]
        self.assertEqual(assistant["reasoning"], "raciocinio completo")
        self.assertEqual(assistant["skill_activities"], [activity])

        exported = TestClient(app).get(
            "/api/v1/export/trace-session?format=json",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(exported.status_code, 200)
        exported_assistant = json.loads(exported.text)["messages"][-1]
        self.assertEqual(exported_assistant["reasoning"], "raciocinio completo")
        self.assertEqual(exported_assistant["skill_activities"], [activity])

        stored = ConversationRepo.get_history(scoped_session, user_id=self.user.id)[-1]
        self.assertEqual(json.loads(stored.skill_activities_json), [activity])


if __name__ == "__main__":
    unittest.main()
