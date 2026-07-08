import tempfile
import unittest
from pathlib import Path

from src.config import settings


class WorkspacePatcherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_user_data_dir = settings.user_data_dir
        settings.user_data_dir = self.tmp.name

    def tearDown(self):
        settings.user_data_dir = self.previous_user_data_dir

    def test_preview_patch_returns_diff_and_expected_checksum(self):
        from src.core.patcher import preview_workspace_patch
        from src.core.workspace import write_text_file

        write_text_file(3, "notes.md", "linha antiga\n")

        preview = preview_workspace_patch(3, "notes.md", "linha nova\n")

        self.assertEqual(preview.path, "notes.md")
        self.assertNotEqual(preview.expected_checksum, preview.new_checksum)
        self.assertIn("-linha antiga", preview.diff)
        self.assertIn("+linha nova", preview.diff)

    def test_apply_patch_requires_checksum_and_saves_snapshot(self):
        from src.core.patcher import apply_workspace_patch, preview_workspace_patch
        from src.core.workspace import read_text_file, write_text_file

        write_text_file(3, "notes.md", "antes\n")
        preview = preview_workspace_patch(3, "notes.md", "depois\n")

        result = apply_workspace_patch(3, "notes.md", "depois\n", preview.expected_checksum)

        self.assertTrue(result.applied)
        self.assertEqual(read_text_file(3, "notes.md"), "depois\n")
        snapshot = Path(self.tmp.name) / "3" / "workspace" / result.snapshot_path
        self.assertTrue(snapshot.is_file())
        self.assertEqual(snapshot.read_text(encoding="utf-8"), "antes\n")

    def test_apply_patch_blocks_when_file_changed_after_preview(self):
        from src.core.patcher import apply_workspace_patch, preview_workspace_patch
        from src.core.workspace import read_text_file, write_text_file

        write_text_file(3, "notes.md", "antes\n")
        preview = preview_workspace_patch(3, "notes.md", "depois\n")
        write_text_file(3, "notes.md", "mudou\n")

        with self.assertRaises(ValueError):
            apply_workspace_patch(3, "notes.md", "depois\n", preview.expected_checksum)

        self.assertEqual(read_text_file(3, "notes.md"), "mudou\n")


if __name__ == "__main__":
    unittest.main()
