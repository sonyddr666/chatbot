import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.app import app
from src.config import settings
from src.core.auth import create_access_token
from src.db.models import init_db
from src.db.repository import UserRepo


class WorkspaceRoutesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_user_data_dir = settings.user_data_dir
        self.previous_database_url = settings.database_url
        settings.user_data_dir = self.tmp.name
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path(f"C:/tmp/chatbot_workspace_routes_{uuid.uuid4().hex}.db")
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        init_db()
        self.user = UserRepo.create_user(
            "workspace-routes@example.test",
            f"workspace_routes_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Workspace Routes",
        )
        token = create_access_token(self.user.id, self.user.username)
        self.headers = {"Authorization": f"Bearer {token}"}
        self.client = TestClient(app)

    def tearDown(self):
        settings.user_data_dir = self.previous_user_data_dir
        settings.database_url = self.previous_database_url

    def test_workspace_routes_require_authentication(self):
        response = self.client.get("/api/v1/workspace/tree")

        self.assertEqual(response.status_code, 401)

    def test_workspace_file_lifecycle(self):
        mkdir_response = self.client.post(
            "/api/v1/workspace/mkdir",
            headers=self.headers,
            json={"path": "projetos"},
        )
        write_response = self.client.put(
            "/api/v1/workspace/file",
            headers=self.headers,
            json={"path": "projetos/app.md", "content": "# App"},
        )
        read_response = self.client.get(
            "/api/v1/workspace/file",
            headers=self.headers,
            params={"path": "projetos/app.md"},
        )
        tree_response = self.client.get(
            "/api/v1/workspace/tree",
            headers=self.headers,
            params={"path": "projetos"},
        )
        move_response = self.client.post(
            "/api/v1/workspace/move",
            headers=self.headers,
            json={"source": "projetos/app.md", "target": "archive/app.md"},
        )
        delete_response = self.client.delete(
            "/api/v1/workspace/path",
            headers=self.headers,
            params={"path": "archive/app.md"},
        )

        self.assertEqual(mkdir_response.status_code, 200)
        self.assertEqual(write_response.status_code, 200)
        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(tree_response.status_code, 200)
        self.assertEqual(move_response.status_code, 200)
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(read_response.json()["content"], "# App")
        self.assertEqual(tree_response.json()["nodes"][0]["path"], "projetos/app.md")
        self.assertEqual(move_response.json()["path"], "archive/app.md")
        self.assertEqual(delete_response.json(), {"deleted": True, "path": "archive/app.md"})

    def test_workspace_routes_reject_path_traversal(self):
        response = self.client.put(
            "/api/v1/workspace/file",
            headers=self.headers,
            json={"path": "../escape.md", "content": "fora"},
        )

        self.assertEqual(response.status_code, 400)

    def test_workspace_patch_preview_and_apply_require_expected_checksum(self):
        self.client.put(
            "/api/v1/workspace/file",
            headers=self.headers,
            json={"path": "notes.md", "content": "antes\n"},
        )

        preview_response = self.client.post(
            "/api/v1/workspace/patch/preview",
            headers=self.headers,
            json={"path": "notes.md", "content": "depois\n"},
        )
        apply_response = self.client.post(
            "/api/v1/workspace/patch/apply",
            headers=self.headers,
            json={
                "path": "notes.md",
                "content": "depois\n",
                "expected_checksum": preview_response.json()["expected_checksum"],
            },
        )
        read_response = self.client.get(
            "/api/v1/workspace/file",
            headers=self.headers,
            params={"path": "notes.md"},
        )

        self.assertEqual(preview_response.status_code, 200)
        self.assertIn("-antes", preview_response.json()["diff"])
        self.assertIn("+depois", preview_response.json()["diff"])
        self.assertEqual(apply_response.status_code, 200)
        self.assertTrue(apply_response.json()["applied"])
        self.assertTrue(apply_response.json()["snapshot_path"].startswith(".snapshots/"))
        self.assertEqual(read_response.json()["content"], "depois\n")


if __name__ == "__main__":
    unittest.main()
