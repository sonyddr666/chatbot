import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.api import routes
from src.api.app import app
from src.config import settings
from src.core.auth import create_access_token
from src.db.models import User, get_session_db, init_db
from src.db.repository import UserRepo


class RegistrationApprovalTest(unittest.TestCase):
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
        settings.database_url = f"sqlite:///{(root / 'registration.db').as_posix()}"
        settings.user_data_dir = str(root / "users")
        settings.initial_admin_email = "owner@example.test"
        settings.initial_admin_username = "owner"
        settings.initial_admin_password = "secure-owner-password"
        settings.allow_registration = True
        routes._db_initialized = False
        init_db()
        self.admin = UserRepo.ensure_initial_admin()
        self.admin_headers = {
            "Authorization": f"Bearer {create_access_token(self.admin.id, self.admin.username)}"
        }
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        routes._db_initialized = False
        for name, value in self.previous.items():
            setattr(settings, name, value)
        self.tmp.cleanup()

    @staticmethod
    def registration(email="visitor@example.test", username="visitor"):
        return {
            "email": email,
            "username": username,
            "display_name": "Visitor",
            "password": "secret123",
        }

    def test_pending_registration_requires_admin_approval_before_login(self):
        response = self.client.post("/api/v1/auth/register", json=self.registration())

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "pending")
        self.assertNotIn("access_token", response.json())

        db = get_session_db()
        pending = db.query(User).filter(User.username == "visitor").one()
        pending_id = pending.id
        self.assertFalse(pending.is_active)
        self.assertEqual(pending.registration_status, "pending")
        db.close()

        login = self.client.post(
            "/api/v1/auth/login",
            json={"login": "visitor", "password": "secret123"},
        )
        self.assertEqual(login.status_code, 403)
        self.assertIn("aguardando aprovacao", login.json()["detail"])

        duplicate_email = self.client.post(
            "/api/v1/auth/register",
            json=self.registration(username="another-user"),
        )
        duplicate_username = self.client.post(
            "/api/v1/auth/register",
            json=self.registration(email="another@example.test"),
        )
        self.assertEqual(duplicate_email.status_code, 400)
        self.assertEqual(duplicate_username.status_code, 400)

        users = self.client.get(
            "/api/v1/admin/users?status=pending",
            headers=self.admin_headers,
        )
        self.assertEqual(users.status_code, 200)
        self.assertEqual([user["id"] for user in users.json()], [pending_id])

        approved = self.client.post(
            f"/api/v1/admin/users/{pending_id}/approve",
            headers=self.admin_headers,
        )
        self.assertEqual(approved.status_code, 200)
        self.assertTrue(approved.json()["is_active"])
        self.assertEqual(approved.json()["registration_status"], "approved")

        login = self.client.post(
            "/api/v1/auth/login",
            json={"login": "visitor", "password": "secret123"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("access_token", login.json())

    def test_delete_rejected_request_releases_email_and_username(self):
        created = self.client.post("/api/v1/auth/register", json=self.registration())
        self.assertEqual(created.status_code, 202)

        db = get_session_db()
        pending_id = db.query(User).filter(User.username == "visitor").one().id
        db.close()

        rejected = self.client.post(
            f"/api/v1/admin/users/{pending_id}/reject",
            headers=self.admin_headers,
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["registration_status"], "rejected")

        reserved = self.client.post("/api/v1/auth/register", json=self.registration())
        self.assertEqual(reserved.status_code, 400)

        deleted = self.client.delete(
            f"/api/v1/admin/users/{pending_id}",
            headers=self.admin_headers,
        )
        self.assertEqual(deleted.status_code, 200)

        requested_again = self.client.post("/api/v1/auth/register", json=self.registration())
        self.assertEqual(requested_again.status_code, 202)

    def test_admin_routes_reject_anonymous_access(self):
        response = self.client.get("/api/v1/admin/users?status=all")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
