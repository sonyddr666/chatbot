import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from src.config import settings
from src.core.workspace import read_text_file, write_text_file
from src.core.workspace_rag import ingest_selected_workspace_file
from src.db.models import init_db
from src.db.repository import DocumentRepo, UserRepo


class WorkspaceRagTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_user_data_dir = settings.user_data_dir
        self.previous_database_url = settings.database_url
        settings.user_data_dir = self.tmp.name
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path(f"C:/tmp/chatbot_workspace_rag_{uuid.uuid4().hex}.db")
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        init_db()
        self.user = UserRepo.create_user(
            f"workspace-rag-{uuid.uuid4().hex[:8]}@example.test",
            f"workspace_rag_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Workspace RAG",
        )

    def tearDown(self):
        settings.user_data_dir = self.previous_user_data_dir
        settings.database_url = self.previous_database_url

    def test_workspace_file_enters_rag_only_after_explicit_selection(self):
        write_text_file(self.user.id, "profile/about.md", "Meu dado selecionado")
        self.assertEqual(DocumentRepo.list_all(self.user.id), [])

        with patch("src.core.workspace_rag.add_user_documents", return_value=["workspace-chunk"]):
            result = ingest_selected_workspace_file(self.user.id, "profile/about.md")

        documents = DocumentRepo.list_all(self.user.id)
        self.assertEqual(result["status"], "indexed")
        self.assertEqual(result["chunks"], 1)
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].source, "workspace")
        self.assertEqual(documents[0].filename, "profile/about.md")
        self.assertEqual(read_text_file(self.user.id, "profile/about.md"), "Meu dado selecionado")

    def test_reselecting_workspace_file_replaces_previous_rag_version(self):
        write_text_file(self.user.id, "notes.md", "versao um")
        with patch("src.core.workspace_rag.add_user_documents", return_value=["old-chunk"]):
            ingest_selected_workspace_file(self.user.id, "notes.md")
        write_text_file(self.user.id, "notes.md", "versao dois")

        with (
            patch("src.core.workspace_rag.add_user_documents", return_value=["new-chunk"]),
            patch("src.core.workspace_rag.delete_user_documents") as delete_vectors,
        ):
            ingest_selected_workspace_file(self.user.id, "notes.md")

        documents = DocumentRepo.list_by_source(self.user.id, "workspace")
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].vector_ids_json, '["new-chunk"]')
        delete_vectors.assert_called_once_with(self.user.id, ["old-chunk"])


if __name__ == "__main__":
    unittest.main()
