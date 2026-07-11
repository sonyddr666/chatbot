import asyncio
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage

from src.api.app import app
from src.config import settings
from src.core.auth import create_access_token
from src.core.chat_attachments import save_chat_attachment
from src.core.chat import ChatEngine
from src.core.chat_jobs import process_chat_job
from src.core.llm import _convert_messages_to_codex
from src.db.models import init_db
from src.db.repository import ChatAttachmentRepo, ConversationRepo, UserRepo


class ChatAttachmentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_database_url = settings.database_url
        self.previous_user_data_dir = settings.user_data_dir
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path(f"C:/tmp/chatbot_attachments_{uuid.uuid4().hex}.db")
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        settings.user_data_dir = str(Path(self.tmp.name, "users"))
        init_db()
        self.user = UserRepo.create_user(
            f"attachment-{uuid.uuid4().hex[:8]}@example.test",
            f"attachment_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Attachment",
        )
        token = create_access_token(self.user.id, self.user.username)
        self.headers = {"Authorization": f"Bearer {token}"}
        self.client = TestClient(app)

    def tearDown(self):
        settings.database_url = self.previous_database_url
        settings.user_data_dir = self.previous_user_data_dir

    def test_service_saves_original_inside_real_chat_workspace(self):
        artifact = save_chat_attachment(self.user.id, "notes.md", b"# Dados do usuario", "text/markdown")

        expected_root = Path(settings.user_data_dir) / str(self.user.id) / "workspace" / "chat" / "uploads"
        self.assertTrue(artifact.relative_path.startswith("chat/uploads/att_"))
        self.assertTrue(artifact.relative_path.endswith("/notes.md"))
        self.assertTrue(artifact.relative_path.startswith("chat/uploads/"))
        self.assertTrue((Path(settings.user_data_dir) / str(self.user.id) / "workspace" / artifact.relative_path).is_file())
        self.assertTrue(expected_root.is_dir())
        self.assertIn("Dados do usuario", artifact.extracted_text)

    def test_upload_and_job_attach_file_without_rag_ingestion(self):
        with patch("src.api.routes.add_user_documents") as rag_add:
            upload = self.client.post(
                "/api/v1/chat/attachments",
                headers=self.headers,
                data={"session_id": "files"},
                files=[("files", ("context.md", b"segredo-do-anexo", "text/markdown"))],
            )
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertFalse(upload.json()["rag_indexed"])
        rag_add.assert_not_called()
        attachment = upload.json()["attachments"][0]
        workspace_tree = self.client.get(
            "/api/v1/workspace/tree",
            headers=self.headers,
            params={"path": "chat/uploads"},
        )
        self.assertEqual(workspace_tree.status_code, 200)
        self.assertIn(attachment["id"], [node["name"] for node in workspace_tree.json()["nodes"]])

        body = {
            "message": "O que existe no arquivo?",
            "session_id": "files",
            "client_request_id": f"request-{uuid.uuid4().hex}",
            "attachment_ids": [attachment["id"]],
            "use_rag": False,
            "response_mode": "normal",
            "reasoning_effort": "low",
        }
        with patch("src.api.routes.start_chat_job"):
            created = self.client.post("/api/v1/chat/jobs", headers=self.headers, json=body)
            retried = self.client.post("/api/v1/chat/jobs", headers=self.headers, json=body)

        self.assertEqual(created.status_code, 202, created.text)
        self.assertEqual(retried.status_code, 202, retried.text)
        self.assertEqual(created.json()["id"], retried.json()["id"])
        self.assertEqual(created.json()["attachments"][0]["id"], attachment["id"])

        conversation = self.client.get("/api/v1/conversations/files", headers=self.headers)
        self.assertEqual(conversation.status_code, 200)
        self.assertEqual(len(conversation.json()["messages"]), 2)
        user_message = conversation.json()["messages"][0]
        self.assertEqual(user_message["attachments"][0]["filename"], "context.md")

        model_content = ChatAttachmentRepo.model_content_for_message(
            created.json()["user_message_id"],
            self.user.id,
            body["message"],
        )
        self.assertIsInstance(model_content, str)
        self.assertIn("segredo-do-anexo", model_content)
        self.assertIn("ARQUIVOS ANEXADOS PELO USUARIO", model_content)

        workspace_file = (
            Path(settings.user_data_dir)
            / str(self.user.id)
            / "workspace"
            / attachment["relative_path"]
        )
        workspace_file.write_text("conteudo-editado-no-workspace", encoding="utf-8")
        refreshed_content = ChatAttachmentRepo.model_content_for_message(
            created.json()["user_message_id"],
            self.user.id,
            body["message"],
        )
        self.assertIn("conteudo-editado-no-workspace", refreshed_content)
        self.assertEqual(ConversationRepo.export_for_user(self.user.id)[0]["messages"][0]["content"], body["message"])
        self.assertEqual(self.client.get("/api/v1/documents", headers=self.headers).json(), [])

        captured = {}

        async def fake_chat_stream(_engine, model_input):
            captured["input"] = model_input
            yield ("content", "arquivo lido")

        with (
            patch("src.core.chat_jobs.get_active_config_for_user", return_value={"provider_id": "test"}),
            patch("src.core.chat_jobs.model_requests_workspace", new=AsyncMock(return_value=False)),
            patch("src.core.chat_jobs.user_has_personal_rag", return_value=False),
            patch("src.core.chat_jobs.run_enabled_skill_context", new=AsyncMock(return_value="")),
            patch.object(ChatEngine, "chat_stream", new=fake_chat_stream),
        ):
            asyncio.run(process_chat_job(created.json()["id"]))

        self.assertIn("conteudo-editado-no-workspace", captured["input"])

        with patch("src.core.workspace_rag.add_user_documents", return_value=["optional-rag-chunk"]):
            optional_rag = self.client.post(
                "/api/v1/workspace/rag/ingest",
                headers=self.headers,
                json={"path": attachment["relative_path"]},
            )
        self.assertEqual(optional_rag.status_code, 200, optional_rag.text)
        self.assertEqual(optional_rag.json()["ids"], ["optional-rag-chunk"])

    def test_attachment_download_is_isolated_by_user(self):
        upload = self.client.post(
            "/api/v1/chat/attachments",
            headers=self.headers,
            data={"session_id": "private"},
            files=[("files", ("private.txt", b"private", "text/plain"))],
        )
        attachment_id = upload.json()["attachments"][0]["id"]

        other = UserRepo.create_user(
            f"other-{uuid.uuid4().hex[:8]}@example.test",
            f"other_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Other",
        )
        other_headers = {
            "Authorization": f"Bearer {create_access_token(other.id, other.username)}",
        }

        own_download = self.client.get(
            f"/api/v1/chat/attachments/{attachment_id}/download",
            headers=self.headers,
        )
        other_download = self.client.get(
            f"/api/v1/chat/attachments/{attachment_id}/download",
            headers=other_headers,
        )
        self.assertEqual(own_download.status_code, 200)
        self.assertEqual(own_download.content, b"private")
        self.assertEqual(other_download.status_code, 404)

    def test_file_can_be_sent_without_text_message(self):
        upload = self.client.post(
            "/api/v1/chat/attachments",
            headers=self.headers,
            data={"session_id": "file-only"},
            files=[("files", ("only.md", b"arquivo sem texto no chat", "text/markdown"))],
        )
        attachment = upload.json()["attachments"][0]
        with patch("src.api.routes.start_chat_job"):
            created = self.client.post(
                "/api/v1/chat/jobs",
                headers=self.headers,
                json={
                    "message": "",
                    "session_id": "file-only",
                    "client_request_id": f"request-{uuid.uuid4().hex}",
                    "attachment_ids": [attachment["id"]],
                    "use_rag": False,
                    "response_mode": "normal",
                    "reasoning_effort": "low",
                },
            )

        self.assertEqual(created.status_code, 202, created.text)
        self.assertEqual(created.json()["message"], "")
        self.assertEqual(created.json()["attachments"][0]["filename"], "only.md")

    def test_codex_conversion_keeps_image_input(self):
        messages = [HumanMessage(content=[
            {"type": "text", "text": "Analise a imagem"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
        ])]

        converted = _convert_messages_to_codex(messages)

        self.assertEqual(converted[0]["content"][0]["type"], "input_text")
        self.assertEqual(converted[0]["content"][1]["type"], "input_image")
        self.assertEqual(converted[0]["content"][1]["image_url"], "data:image/png;base64,AA==")


if __name__ == "__main__":
    unittest.main()
