import asyncio
import unittest
import uuid
from pathlib import Path

from src.config import settings
from src.core.skill_runtime import run_enabled_skill_context, runtime_skill_activity
from src.db.models import init_db
from src.db.repository import ConversationRepo, SkillRepo, SkillRunRepo, UserRepo


class ConversationHistorySkillTest(unittest.TestCase):
    def setUp(self):
        self.previous_database_url = settings.database_url
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path(f"C:/tmp/chatbot_history_skill_{uuid.uuid4().hex}.db")
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        init_db()
        self.user = UserRepo.create_user(
            f"history-{uuid.uuid4().hex[:8]}@example.test",
            f"history_{uuid.uuid4().hex[:8]}",
            "secret123",
            "History User",
        )
        self.other = UserRepo.create_user(
            f"other-{uuid.uuid4().hex[:8]}@example.test",
            f"other_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Other User",
        )

    def tearDown(self):
        settings.database_url = self.previous_database_url

    def test_searches_other_chats_for_only_the_current_user(self):
        previous_session = f"u{self.user.id}:previous"
        current_session = f"u{self.user.id}:current"
        other_session = f"u{self.other.id}:private"
        ConversationRepo.add_message(
            previous_session,
            "user",
            "Eu contei que minhas abelhas vivem em uma colmeia azul.",
            user_id=self.user.id,
        )
        ConversationRepo.add_message(
            previous_session,
            "assistant",
            "A colmeia azul foi registrada na conversa.",
            user_id=self.user.id,
        )
        ConversationRepo.add_message(
            current_session,
            "user",
            "Segredo atual sobre abelhas que nao deve voltar pela skill.",
            user_id=self.user.id,
        )
        ConversationRepo.add_message(
            other_session,
            "user",
            "Segredo de outro usuario sobre abelhas.",
            user_id=self.other.id,
        )

        context = asyncio.run(run_enabled_skill_context(
            self.user.id,
            "O que eu falei nos outros chats sobre abelhas?",
            session_id=current_session,
        ))

        self.assertIn("colmeia azul", context)
        self.assertNotIn("Segredo atual", context)
        self.assertNotIn("Segredo de outro usuario", context)
        activity = runtime_skill_activity(context)
        self.assertIsNotNone(activity)
        self.assertEqual(activity["name"], "conversation_history")
        self.assertEqual(activity["label"], "Historico pessoal consultado")
        run = SkillRunRepo.list_for_user(self.user.id, limit=1)[0]
        self.assertEqual(run["skill_name"], "conversation_history")
        self.assertEqual(run["status"], "completed")

    def test_does_not_read_history_without_an_explicit_trigger(self):
        ConversationRepo.add_message(
            f"u{self.user.id}:previous",
            "user",
            "Minhas abelhas vivem em uma colmeia azul.",
            user_id=self.user.id,
        )

        context = asyncio.run(run_enabled_skill_context(
            self.user.id,
            "Explique como vivem as abelhas",
            session_id=f"u{self.user.id}:current",
        ))

        self.assertEqual(context, "")


if __name__ == "__main__":
    unittest.main()
