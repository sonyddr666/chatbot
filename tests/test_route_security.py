import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.params import Depends
from fastapi.testclient import TestClient

from src.api.app import app
from src.api.routes import router
from src.api.workspace_routes import router as workspace_router
from src.config import settings
from src.core.auth import create_access_token
from src.db.models import init_db
from src.db.repository import UserRepo


class RouteSecurityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.previous_database_url = settings.database_url
        self.previous_user_data_dir = settings.user_data_dir
        self.previous_initial_admin = (
            settings.initial_admin_email,
            settings.initial_admin_username,
            settings.initial_admin_password,
        )
        root = Path(self.tmp.name)
        settings.database_url = f"sqlite:///{(root / 'security.db').as_posix()}"
        settings.user_data_dir = str(root / "users")
        settings.initial_admin_email = "admin@example.test"
        settings.initial_admin_username = "admin"
        settings.initial_admin_password = "secure-test-password"
        init_db()

    def tearDown(self):
        settings.database_url = self.previous_database_url
        settings.user_data_dir = self.previous_user_data_dir
        (
            settings.initial_admin_email,
            settings.initial_admin_username,
            settings.initial_admin_password,
        ) = self.previous_initial_admin
        self.tmp.cleanup()

    def test_legacy_unauthenticated_websocket_file_is_removed(self):
        self.assertFalse(Path("src/api/ws_routes.py").exists())

    def test_sensitive_routes_require_current_user_dependency(self):
        sensitive_prefixes = (
            "/providers",
            "/codex",
            "/profiles",
            "/config",
            "/metrics",
            "/workspace",
            "/skills",
            "/preferences",
            "/preference-suggestions",
        )
        violations = []

        for route in [*router.routes, *workspace_router.routes]:
            path = getattr(route, "path", "")
            if not path.startswith(sensitive_prefixes):
                continue
            signature = inspect.signature(route.endpoint)
            user_param = signature.parameters.get("user")
            default = user_param.default if user_param else None
            if not isinstance(default, Depends):
                violations.append(path)

        self.assertEqual(violations, [])

    def test_non_admin_cannot_mutate_global_provider_api_key(self):
        user = UserRepo.create_user("normal@example.test", "normal", "secret123", "Normal")
        token = create_access_token(user.id, user.username)
        client = TestClient(app)

        with patch("src.api.routes.pm_set_api_key", return_value=True) as set_key:
            response = client.put(
                "/api/v1/providers/manage/opencode-zen-free/api-key",
                headers={"Authorization": f"Bearer {token}"},
                json={"api_key": "should-not-write"},
            )

        self.assertEqual(response.status_code, 403)
        set_key.assert_not_called()

    def test_admin_can_mutate_global_provider_api_key(self):
        admin = UserRepo.ensure_initial_admin()
        token = create_access_token(admin.id, admin.username)
        client = TestClient(app)

        with patch("src.api.routes.pm_set_api_key", return_value=True) as set_key:
            response = client.put(
                "/api/v1/providers/manage/opencode-zen-free/api-key",
                headers={"Authorization": f"Bearer {token}"},
                json={"api_key": "admin-write"},
            )

        self.assertEqual(response.status_code, 200)
        set_key.assert_called_once_with("opencode-zen-free", "admin-write")


if __name__ == "__main__":
    unittest.main()
