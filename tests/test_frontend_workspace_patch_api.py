import unittest
from pathlib import Path


class FrontendWorkspacePatchApiTest(unittest.TestCase):
    def test_frontend_exposes_workspace_patch_api(self):
        api_ts = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")

        self.assertIn("WorkspacePatchPreview", api_ts)
        self.assertIn("WorkspacePatchApplyResult", api_ts)
        self.assertIn("workspacePatchPreview", api_ts)
        self.assertIn("workspacePatchApply", api_ts)
        self.assertIn("/workspace/patch/preview", api_ts)
        self.assertIn("/workspace/patch/apply", api_ts)


if __name__ == "__main__":
    unittest.main()
