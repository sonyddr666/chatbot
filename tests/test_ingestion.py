import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.app import app
from src.config import settings
from src.core.auth import create_access_token
from src.db.models import init_db
from src.db.repository import UserRepo


class IngestionServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_user_data_dir = settings.user_data_dir
        settings.user_data_dir = self.tmp.name

    def tearDown(self):
        settings.user_data_dir = self.previous_user_data_dir

    def test_save_upload_original_stores_bytes_under_user_uploads(self):
        from src.core.ingestion import save_upload_original

        artifact = save_upload_original(5, "notes.md", b"# Notes")

        self.assertEqual(artifact.user_id, 5)
        self.assertEqual(artifact.original_filename, "notes.md")
        self.assertEqual(artifact.size, 7)
        self.assertEqual(artifact.extension, ".md")
        self.assertTrue(artifact.storage_path.is_file())
        self.assertEqual(artifact.storage_path.read_bytes(), b"# Notes")
        self.assertEqual(artifact.relative_path.split("/")[0], "original")
        self.assertIn("/notes.md", artifact.relative_path)

    def test_save_upload_original_sanitizes_filename_paths(self):
        from src.core.ingestion import save_upload_original

        artifact = save_upload_original(5, "../escape.md", b"safe")

        self.assertEqual(artifact.original_filename, "escape.md")
        self.assertTrue(artifact.storage_path.is_file())
        self.assertTrue(str(artifact.storage_path).startswith(str(Path(self.tmp.name).resolve())))

    def test_extract_text_for_ingestion_accepts_text_formats(self):
        from src.core.ingestion import extract_text_for_ingestion

        self.assertEqual(extract_text_for_ingestion("notes.md", "# Ola".encode("utf-8")), "# Ola")
        self.assertEqual(extract_text_for_ingestion("data.json", b'{"ok": true}'), '{"ok": true}')
        self.assertEqual(extract_text_for_ingestion("table.csv", b"a,b\n1,2"), "a,b\n1,2")

    def test_extract_text_for_ingestion_rejects_pdf_and_docx_without_parser(self):
        from src.core.ingestion import extract_text_for_ingestion

        with self.assertRaises(ValueError):
            extract_text_for_ingestion("file.pdf", b"%PDF-1.4")
        with self.assertRaises(ValueError):
            extract_text_for_ingestion("file.docx", b"PK\x03\x04")

    def test_extract_text_for_ingestion_rejects_unknown_extension(self):
        from src.core.ingestion import extract_text_for_ingestion

        with self.assertRaises(ValueError):
            extract_text_for_ingestion("image.png", b"\x89PNG")

    def _create_auth_headers(self):
        previous_database_url = settings.database_url
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path(f"C:/tmp/chatbot_ingestion_{uuid.uuid4().hex}.db")
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        self.addCleanup(lambda: setattr(settings, "database_url", previous_database_url))
        init_db()
        user = UserRepo.create_user(
            f"ingestion-{uuid.uuid4().hex[:8]}@example.test",
            f"ingestion_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Ingestion",
        )
        token = create_access_token(user.id, user.username)
        return user, {"Authorization": f"Bearer {token}"}

    def test_upload_route_saves_original_before_rag_ingestion(self):
        user, headers = self._create_auth_headers()
        client = TestClient(app)

        with patch("src.api.routes.add_documents", return_value=["chunk-1"]):
            response = client.post(
                "/api/v1/upload",
                headers=headers,
                files={"file": ("notes.md", b"# Notes", "text/markdown")},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["filename"], "notes.md")
        self.assertEqual(data["size"], 7)
        self.assertEqual(data["chunks"], 1)
        self.assertEqual(data["upload_path"].split("/")[0], "original")
        saved = list((Path(self.tmp.name) / str(user.id) / "uploads" / "original").glob("*/notes.md"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_bytes(), b"# Notes")

    def test_upload_route_rejects_pdf_without_parser_instead_of_indexing_binary(self):
        _, headers = self._create_auth_headers()
        client = TestClient(app)

        with patch("src.api.routes.add_documents", return_value=["should-not-be-used"]) as add_mock:
            response = client.post(
                "/api/v1/upload",
                headers=headers,
                files={"file": ("file.pdf", b"%PDF-1.4", "application/pdf")},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Parser para .pdf", response.json()["detail"])
        add_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
