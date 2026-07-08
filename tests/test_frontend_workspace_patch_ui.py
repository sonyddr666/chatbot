import unittest
from pathlib import Path


class FrontendWorkspacePatchUiTest(unittest.TestCase):
    def test_workspace_panel_exposes_approved_patch_flow(self):
        workspace_panel = Path("frontend/src/components/WorkspacePanel.tsx").read_text(encoding="utf-8")
        diff_viewer_path = Path("frontend/src/components/DiffViewer.tsx")

        self.assertTrue(diff_viewer_path.exists(), "DiffViewer.tsx deve existir")
        diff_viewer = diff_viewer_path.read_text(encoding="utf-8")

        self.assertIn("DiffViewer", workspace_panel)
        self.assertIn("workspacePatchPreview", workspace_panel)
        self.assertIn("workspacePatchApply", workspace_panel)
        self.assertIn("Preview patch", workspace_panel)
        self.assertIn("Aplicar patch aprovado", workspace_panel)

        self.assertIn("Preview de alteracao", diff_viewer)
        self.assertIn("expected_checksum", diff_viewer)
        self.assertIn("Aplicar patch aprovado", diff_viewer)
        self.assertIn("Cancelar", diff_viewer)


if __name__ == "__main__":
    unittest.main()
