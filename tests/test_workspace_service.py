import tempfile
import unittest
from pathlib import Path

from src.config import settings


class WorkspaceServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_user_data_dir = settings.user_data_dir
        settings.user_data_dir = self.tmp.name

    def tearDown(self):
        settings.user_data_dir = self.previous_user_data_dir

    def test_write_and_read_text_file_inside_user_workspace(self):
        from src.core.workspace import read_text_file, write_text_file

        info = write_text_file(1, "projetos/app.md", "# App\nconteudo")
        content = read_text_file(1, "projetos/app.md")

        self.assertEqual(info.path, "projetos/app.md")
        self.assertEqual(info.name, "app.md")
        self.assertEqual(info.kind, "file")
        self.assertEqual(content, "# App\nconteudo")
        self.assertTrue((Path(self.tmp.name) / "1" / "workspace" / "projetos" / "app.md").is_file())

    def test_list_tree_returns_only_requested_workspace_nodes(self):
        from src.core.workspace import list_tree, mkdir, write_text_file

        mkdir(1, "projetos")
        write_text_file(1, "projetos/app.md", "ok")
        write_text_file(1, "notes.md", "raiz")

        root_nodes = list_tree(1)
        project_nodes = list_tree(1, "projetos")

        self.assertEqual([node.name for node in root_nodes], ["notes.md", "projetos"])
        self.assertEqual([node.name for node in project_nodes], ["app.md"])

    def test_delete_path_removes_file_and_empty_folder(self):
        from src.core.workspace import delete_path, mkdir, write_text_file

        write_text_file(1, "notes.md", "raiz")
        mkdir(1, "empty")

        self.assertTrue(delete_path(1, "notes.md"))
        self.assertTrue(delete_path(1, "empty"))
        self.assertFalse((Path(self.tmp.name) / "1" / "workspace" / "notes.md").exists())
        self.assertFalse((Path(self.tmp.name) / "1" / "workspace" / "empty").exists())

    def test_delete_path_rejects_non_empty_folder(self):
        from src.core.workspace import delete_path, write_text_file

        write_text_file(1, "projetos/app.md", "ok")

        with self.assertRaises(ValueError):
            delete_path(1, "projetos")

    def test_delete_path_rejects_workspace_root(self):
        from src.core.userspace import safe_user_path
        from src.core.workspace import delete_path

        workspace_root = safe_user_path(1, "workspace")

        with self.assertRaises(ValueError):
            delete_path(1, "")

        self.assertTrue(workspace_root.is_dir())

    def test_move_path_moves_file_without_overwriting(self):
        from src.core.workspace import move_path, read_text_file, write_text_file

        write_text_file(1, "old.md", "conteudo")
        write_text_file(1, "exists.md", "ja existe")

        info = move_path(1, "old.md", "archive/new.md")

        self.assertEqual(info.path, "archive/new.md")
        self.assertEqual(read_text_file(1, "archive/new.md"), "conteudo")
        with self.assertRaises(FileExistsError):
            move_path(1, "archive/new.md", "exists.md")

    def test_move_path_rejects_workspace_root_or_empty_target(self):
        from src.core.userspace import safe_user_path
        from src.core.workspace import move_path, write_text_file

        workspace_root = safe_user_path(1, "workspace")
        write_text_file(1, "notes.md", "conteudo")

        with self.assertRaises(ValueError):
            move_path(1, "", "archive/root")
        with self.assertRaises(ValueError):
            move_path(1, "notes.md", "")

        self.assertTrue(workspace_root.is_dir())
        self.assertTrue((workspace_root / "notes.md").is_file())

    def test_workspace_blocks_path_traversal(self):
        from src.core.workspace import read_text_file, write_text_file

        with self.assertRaises(ValueError):
            write_text_file(1, "../escape.md", "fora")
        with self.assertRaises(ValueError):
            read_text_file(1, "../escape.md")

    def test_read_text_file_rejects_large_files(self):
        from src.core.userspace import safe_user_path
        from src.core.workspace import read_text_file

        path = safe_user_path(1, "workspace", "big.txt")
        path.write_bytes(b"x" * (1024 * 1024 + 1))

        with self.assertRaises(ValueError):
            read_text_file(1, "big.txt")

    def test_user_workspaces_are_isolated_by_root(self):
        from src.core.workspace import list_tree, write_text_file

        write_text_file(1, "same.md", "usuario 1")
        write_text_file(2, "same.md", "usuario 2")

        self.assertEqual((Path(self.tmp.name) / "1" / "workspace" / "same.md").read_text(), "usuario 1")
        self.assertEqual((Path(self.tmp.name) / "2" / "workspace" / "same.md").read_text(), "usuario 2")
        self.assertEqual([node.path for node in list_tree(1)], ["same.md"])
        self.assertEqual([node.path for node in list_tree(2)], ["same.md"])


if __name__ == "__main__":
    unittest.main()
