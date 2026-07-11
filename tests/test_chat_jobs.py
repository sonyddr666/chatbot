import asyncio
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.config import settings
from src.core.chat import ChatEngine
from src.core.chat_jobs import process_chat_job
from src.core.workspace_agent import workspace_request_candidate
from src.db.models import init_db
from src.db.repository import ChatJobRepo, ConversationRepo, MessageRepo, UserRepo


class ChatJobPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.previous_database_url = settings.database_url
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path(f"C:/tmp/chatbot_jobs_{uuid.uuid4().hex}.db")
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        init_db()
        self.user = UserRepo.create_user(
            f"jobs-{uuid.uuid4().hex[:8]}@example.test",
            f"jobs_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Jobs",
        )

    def tearDown(self):
        settings.database_url = self.previous_database_url

    def test_job_persists_partial_text_reasoning_and_ordered_events(self):
        job = ChatJobRepo.create_with_messages(
            user_id=self.user.id,
            session_id=f"u{self.user.id}:jobs",
            message="Explique SSE",
            provider={"provider_id": "codex", "model_id": "gpt-test"},
            response_mode="thinking",
            reasoning_effort="high",
            use_rag=False,
        )
        ChatJobRepo.set_running(job["id"])
        first = ChatJobRepo.add_event(job["id"], "reasoning", "Analisando. ")
        second = ChatJobRepo.add_event(job["id"], "text_delta", "Resposta parcial")
        ChatJobRepo.finish(job["id"], "completed")

        snapshot = ChatJobRepo.get(job["id"], self.user.id)
        events = ChatJobRepo.list_events(job["id"], self.user.id, after_id=first)
        self.assertEqual(snapshot["content"], "Resposta parcial")
        self.assertEqual(snapshot["reasoning"], "Analisando. ")
        self.assertEqual(snapshot["status"], "completed")
        self.assertTrue(MessageRepo.mark_read(snapshot["assistant_message_id"], self.user.id))
        self.assertEqual(events[0]["id"], second)
        self.assertEqual(events[-1]["type"], "done")

    def test_workspace_router_skips_messages_without_file_intent(self):
        self.assertFalse(workspace_request_candidate("oi"))
        self.assertFalse(workspace_request_candidate("coloca uma estante no predio"))
        self.assertTrue(workspace_request_candidate("crie um arquivo notas.md"))
        self.assertTrue(workspace_request_candidate("edita ele"))

    def test_client_request_id_reuses_job_without_duplicate_messages(self):
        request_id = f"request-{uuid.uuid4().hex}"
        params = {
            "user_id": self.user.id,
            "session_id": f"u{self.user.id}:retry",
            "message": "Continue mesmo se a aba fechar",
            "provider": {"provider_id": "codex", "model_id": "gpt-test"},
            "response_mode": "normal",
            "reasoning_effort": "low",
            "use_rag": False,
            "client_request_id": request_id,
        }

        first = ChatJobRepo.create_with_messages(**params)
        retried = ChatJobRepo.create_with_messages(**params)

        self.assertEqual(first["id"], retried["id"])
        self.assertEqual(retried["client_request_id"], request_id)
        conversations = ConversationRepo.export_for_user(self.user.id, params["session_id"])
        self.assertEqual(len(conversations), 1)
        self.assertEqual(len(conversations[0]["messages"]), 2)

        changed = dict(params, message="Outro pedido")
        with self.assertRaisesRegex(ValueError, "client_request_id"):
            ChatJobRepo.create_with_messages(**changed)

    def test_only_one_worker_claims_a_queued_job(self):
        job = ChatJobRepo.create_with_messages(
            user_id=self.user.id,
            session_id=f"u{self.user.id}:claim",
            message="Teste de claim",
            provider={"provider_id": "codex", "model_id": "gpt-test"},
            response_mode="normal",
            reasoning_effort="low",
            use_rag=False,
            client_request_id=f"request-{uuid.uuid4().hex}",
        )
        self.assertTrue(ChatJobRepo.claim_queued(job["id"]))
        self.assertFalse(ChatJobRepo.claim_queued(job["id"]))

    def test_fast_two_word_search_does_not_bypass_skills(self):
        job = ChatJobRepo.create_with_messages(
            user_id=self.user.id,
            session_id=f"u{self.user.id}:short-search",
            message="pesquisa meme",
            provider={"provider_id": "test", "model_id": "test"},
            response_mode="normal",
            reasoning_effort="low",
            use_rag=False,
        )

        async def fake_stream(_engine, _message):
            yield ("content", "resultado")

        runtime = AsyncMock(return_value="contexto da pesquisa")
        with (
            patch("src.core.chat_jobs.get_active_config_for_user", return_value={"provider_id": "test"}),
            patch("src.core.chat_jobs.model_requests_workspace", new=AsyncMock(return_value=False)),
            patch("src.core.chat_jobs.user_has_personal_rag", return_value=False),
            patch("src.core.chat_jobs.run_enabled_skill_context", new=runtime),
            patch.object(ChatEngine, "chat_stream", new=fake_stream),
        ):
            asyncio.run(process_chat_job(job["id"]))

        runtime.assert_awaited_once_with(
            self.user.id,
            "pesquisa meme",
            session_id=f"u{self.user.id}:short-search",
        )


if __name__ == "__main__":
    unittest.main()
