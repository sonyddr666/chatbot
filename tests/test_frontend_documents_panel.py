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


if __name__ == "__main__":
    unittest.main()
