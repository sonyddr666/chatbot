import unittest
from pathlib import Path


class FrontendDocumentsPanelTest(unittest.TestCase):
    def test_documents_panel_is_wired_to_app_and_document_api(self):
        app_tsx = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
        panel_path = Path("frontend/src/components/DocumentsPanel.tsx")

        self.assertTrue(panel_path.exists(), "DocumentsPanel.tsx deve existir")
        panel = panel_path.read_text(encoding="utf-8")

        self.assertIn("DocumentsPanel", app_tsx)
        self.assertIn("documentsOpen", app_tsx)
        self.assertIn("setDocumentsOpen(true)", app_tsx)
        self.assertIn("title=\"Documentos RAG\"", app_tsx)

        self.assertIn("Documentos RAG", panel)
        self.assertIn("api.listDocuments", panel)
        self.assertIn("api.uploadDocument", panel)
        self.assertIn("api.deleteDocument", panel)
        self.assertIn("Arraste arquivos", panel)

    def test_documents_panel_shows_ingestion_status_and_errors(self):
        api_ts = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")
        panel = Path("frontend/src/components/DocumentsPanel.tsx").read_text(encoding="utf-8")

        for field in (
            "source",
            "upload_path",
            "checksum",
            "status",
            "parser",
            "error_message",
        ):
            self.assertIn(field, api_ts)

        self.assertIn("document.status", panel)
        self.assertIn("document.parser", panel)
        self.assertIn("document.source", panel)
        self.assertIn("document.error_message", panel)
        self.assertIn("Erro na ingestao", panel)

    def test_failed_upload_refreshes_document_list_for_recorded_errors(self):
        panel = Path("frontend/src/components/DocumentsPanel.tsx").read_text(encoding="utf-8")
        upload_fn = panel.split("const uploadFile", 1)[1].split("const deleteDocument", 1)[0]
        upload_catch = upload_fn.split("catch (err)", 1)[1].split("finally", 1)[0]

        self.assertIn("await loadDocuments()", upload_catch)


if __name__ == "__main__":
    unittest.main()
