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
from src.core.chat_attachments import build_model_user_content, save_chat_attachment
from src.core.chat import ChatEngine
from src.core.chat_jobs import process_chat_job
from src.core.file_delivery import requests_file_delivery, resolve_file_delivery
from src.core.llm import _convert_messages_to_codex
from src.core.workspace import write_text_file
from src.db.models import init_db
from src.db.repository import ChatAttachmentRepo, ChatJobRepo, ConversationRepo, UserRepo


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

    def test_svg_and_arbitrary_binary_are_accepted_without_automatic_rag(self):
        svg = self.client.post(
            "/api/v1/chat/attachments",
            headers=self.headers,
            data={"session_id": "anything"},
            files=[(
                "files",
                ("drawing.svg", b'<svg><text id="answer">conteudo-svg</text></svg>', "image/svg+xml"),
            )],
        )
        binary = self.client.post(
            "/api/v1/chat/attachments",
            headers=self.headers,
            data={"session_id": "anything"},
            files=[("files", ("archive.unknown", b"\x00\xff\x00\x81", "application/octet-stream"))],
        )

        self.assertEqual(svg.status_code, 200, svg.text)
        self.assertEqual(binary.status_code, 200, binary.text)
        self.assertFalse(svg.json()["rag_indexed"])
        self.assertEqual(svg.json()["attachments"][0]["kind"], "text")
        self.assertEqual(binary.json()["attachments"][0]["kind"], "binary")

        binary_attachment = binary.json()["attachments"][0]
        svg_content = build_model_user_content(
            self.user.id,
            "Leia o SVG",
            [svg.json()["attachments"][0]],
        )
        binary_content = build_model_user_content(
            self.user.id,
            "Guarde o binario",
            [binary_attachment],
        )
        self.assertIn("conteudo-svg", svg_content)
        self.assertIn("formato binario nao decodificado", binary_content)

        binary_download = self.client.get(
            f'/api/v1/chat/attachments/{binary_attachment["id"]}/download',
            headers=self.headers,
        )
        self.assertEqual(binary_download.status_code, 200)
        self.assertEqual(binary_download.content, b"\x00\xff\x00\x81")

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

    def test_assistant_returns_previous_upload_as_downloadable_attachment(self):
        upload = self.client.post(
            "/api/v1/chat/attachments",
            headers=self.headers,
            data={"session_id": "return-file"},
            files=[("files", ("resultado.json", b'{"ok": true}', "application/json"))],
        )
        attachment = upload.json()["attachments"][0]
        with patch("src.api.routes.start_chat_job"):
            original = self.client.post(
                "/api/v1/chat/jobs",
                headers=self.headers,
                json={
                    "message": "guarde este arquivo",
                    "session_id": "return-file",
                    "attachment_ids": [attachment["id"]],
                    "response_mode": "normal",
                    "reasoning_effort": "low",
                },
            )
        ChatJobRepo.finish(original.json()["id"], "completed")

        with patch("src.api.routes.start_chat_job"):
            delivery = self.client.post(
                "/api/v1/chat/jobs",
                headers=self.headers,
                json={
                    "message": "me envie o arquivo de volta",
                    "session_id": "return-file",
                    "response_mode": "normal",
                    "reasoning_effort": "low",
                },
            )

        self.assertEqual(delivery.status_code, 202, delivery.text)
        with patch(
            "src.core.chat_jobs.get_active_config_for_user",
            side_effect=AssertionError("file delivery must not call a model provider"),
        ):
            asyncio.run(process_chat_job(delivery.json()["id"]))

        snapshot = ChatJobRepo.get(delivery.json()["id"], self.user.id)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["assistant_attachments"][0]["id"], attachment["id"])
        self.assertIn("resultado.json", snapshot["content"])
        events = ChatJobRepo.list_events(delivery.json()["id"], self.user.id)
        self.assertIn("attachment", [event["type"] for event in events])

        conversation = self.client.get("/api/v1/conversations/return-file", headers=self.headers).json()
        assistant = conversation["messages"][-1]
        self.assertEqual(assistant["attachments"][0]["filename"], "resultado.json")
        download = self.client.get(
            f'/api/v1/chat/attachments/{attachment["id"]}/download',
            headers=self.headers,
        )
        self.assertEqual(download.content, b'{"ok": true}')

    def test_assistant_can_deliver_file_created_in_workspace(self):
        write_text_file(self.user.id, "relatorios/relatorio.md", "# Resultado final")
        job = ChatJobRepo.create_with_messages(
            user_id=self.user.id,
            session_id=f"u{self.user.id}:workspace-delivery",
            message="me envie o arquivo relatorio.md que voce criou",
            provider={"provider_id": "unused", "model_id": "unused"},
            response_mode="normal",
            reasoning_effort="low",
            use_rag=False,
        )

        asyncio.run(process_chat_job(job["id"]))

        snapshot = ChatJobRepo.get(job["id"], self.user.id)
        delivered = snapshot["assistant_attachments"][0]
        self.assertEqual(delivered["relative_path"], "relatorios/relatorio.md")
        self.assertEqual(delivered["filename"], "relatorio.md")
        download = self.client.get(
            f'/api/v1/chat/attachments/{delivered["id"]}/download',
            headers=self.headers,
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"# Resultado final")

    def test_file_delivery_is_explicit_and_never_crosses_users(self):
        self.assertTrue(requests_file_delivery("me envie o arquivo de volta"))
        self.assertTrue(requests_file_delivery("@arquivo relatorio.pdf"))
        self.assertFalse(requests_file_delivery("vamos conversar sobre um arquivo"))
        self.assertFalse(requests_file_delivery("crie um arquivo e me envie"))
        self.assertFalse(requests_file_delivery(
            "me responde oq verity na porra da pesquisa seu merrda inutil"
        ))
        self.assertFalse(requests_file_delivery("pesquisa e me envie o arquivo"))

        other = UserRepo.create_user(
            f"delivery-other-{uuid.uuid4().hex[:8]}@example.test",
            f"delivery_other_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Other",
        )
        write_text_file(other.id, "segredo.txt", "somente do outro usuario")
        selected = resolve_file_delivery(
            self.user.id,
            f"u{self.user.id}:private",
            "me envie o arquivo segredo.txt",
        )
        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
