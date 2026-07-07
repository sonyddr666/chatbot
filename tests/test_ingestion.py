import tempfile
import unittest
import uuid
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from docx import Document
from fastapi.testclient import TestClient

from src.api.app import app
from src.config import settings
from src.core.auth import create_access_token
from src.db.models import init_db
from src.db.repository import UserRepo


def make_pdf_bytes(text: str) -> bytes:
    stream = f"BT /F1 24 Tf 100 700 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        b"5 0 obj << /Length " + str(len(stream)).encode("ascii") + b" >> stream\n" + stream + b"\nendstream endobj\n",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf += obj
    xref_start = len(pdf)
    xref_entries = [b"0000000000 65535 f \n"]
    xref_entries.extend(f"{offset:010d} 00000 n \n".encode("ascii") for offset in offsets[1:])
    pdf += b"xref\n0 6\n" + b"".join(xref_entries)
    pdf += b"trailer << /Root 1 0 R /Size 6 >>\n"
    pdf += b"startxref\n" + str(xref_start).encode("ascii") + b"\n%%EOF\n"
    return pdf


MINIMAL_TEXT_PDF = make_pdf_bytes("Hello PDF")


def make_docx_bytes(*paragraphs: str) -> bytes:
    doc = Document()
    for paragraph in paragraphs:
        doc.add_paragraph(paragraph)
    output = BytesIO()
    doc.save(output)
    return output.getvalue()


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

    def test_extract_text_for_ingestion_accepts_pdf_and_docx(self):
        from src.core.ingestion import extract_text_for_ingestion

        docx_bytes = make_docx_bytes("Hello DOCX", "Second line")

        self.assertIn("Hello PDF", extract_text_for_ingestion("file.pdf", MINIMAL_TEXT_PDF))
        self.assertEqual(
            extract_text_for_ingestion("file.docx", docx_bytes),
            "Hello DOCX\nSecond line",
        )

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

    def test_upload_route_ingests_pdf_with_real_parser(self):
        _, headers = self._create_auth_headers()
        client = TestClient(app)

        with patch("src.api.routes.add_documents", return_value=["pdf-chunk"]) as add_mock:
            response = client.post(
                "/api/v1/upload",
                headers=headers,
                files={"file": ("file.pdf", MINIMAL_TEXT_PDF, "application/pdf")},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["filename"], "file.pdf")
        self.assertEqual(data["ids"], ["pdf-chunk"])
        indexed_texts = add_mock.call_args.args[0]
        self.assertTrue(any("Hello PDF" in text for text in indexed_texts))


if __name__ == "__main__":
    unittest.main()
