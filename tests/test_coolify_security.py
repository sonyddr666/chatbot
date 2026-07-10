import tempfile
import unittest
from pathlib import Path

from src.config import settings
from src.core.auth import verify_password
from src.db.models import init_db
from src.db.repository import UserRepo


class CoolifySecurityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.previous = {
            "database_url": settings.database_url,
            "user_data_dir": settings.user_data_dir,
            "initial_admin_email": settings.initial_admin_email,
            "initial_admin_username": settings.initial_admin_username,
            "initial_admin_password": settings.initial_admin_password,
            "allow_registration": settings.allow_registration,
        }
        root = Path(self.tmp.name)
        settings.database_url = f"sqlite:///{(root / 'coolify.db').as_posix()}"
        settings.user_data_dir = str(root / "users")
        settings.initial_admin_email = "owner@example.test"
        settings.initial_admin_username = "owner"
        settings.initial_admin_password = "first-secure-password"
        settings.allow_registration = False
        init_db()

    def tearDown(self):
        for name, value in self.previous.items():
            setattr(settings, name, value)
        self.tmp.cleanup()

    def test_bootstrap_admin_is_created_without_public_defaults(self):
        admin = UserRepo.ensure_initial_admin()

        self.assertEqual(admin.email, "owner@example.test")
        self.assertEqual(admin.username, "owner")
        self.assertTrue(admin.is_admin)
        self.assertTrue(verify_password("first-secure-password", admin.password_hash))

    def test_restart_does_not_reset_existing_admin_password(self):
        first = UserRepo.ensure_initial_admin()
        settings.initial_admin_password = "different-secure-password"

        second = UserRepo.ensure_initial_admin()

        self.assertEqual(first.id, second.id)
        self.assertTrue(verify_password("first-secure-password", second.password_hash))
        self.assertFalse(verify_password("different-secure-password", second.password_hash))

    def test_public_registration_is_disabled(self):
        from fastapi.testclient import TestClient
        from src.api.app import app

        response = TestClient(app).post(
            "/api/v1/auth/register",
            json={
                "email": "visitor@example.test",
                "username": "visitor",
                "password": "secret123",
            },
        )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
