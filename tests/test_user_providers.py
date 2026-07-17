import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.app import app
from src.config import settings
from src.core.auth import create_access_token
from src.core.provider_manager import get_active_config
from src.db.models import init_db
from src.db.repository import UserRepo


class UserProviderConfigTest(unittest.TestCase):
    def setUp(self):
        self.previous_database_url = settings.database_url
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path(f"C:/tmp/chatbot_user_providers_{uuid.uuid4().hex}.db")
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        init_db()
        self.user = UserRepo.create_user(
            f"user-provider-{uuid.uuid4().hex[:8]}@example.test",
            f"user_provider_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Provider User",
        )
        self.other = UserRepo.create_user(
            f"other-provider-{uuid.uuid4().hex[:8]}@example.test",
            f"other_provider_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Other Provider User",
        )

    def tearDown(self):
        settings.database_url = self.previous_database_url

    def test_user_provider_config_is_isolated_and_masks_api_key(self):
        from src.core.user_provider_manager import (
            create_user_provider,
            get_active_config_for_user,
            list_user_providers,
        )

        self.assertEqual(get_active_config_for_user(self.user.id)["provider_id"], "opencode-zen-free")

        created = create_user_provider(
            self.user.id,
            {
                "provider_id": "personal-openai",
                "display_name": "Meu OpenAI",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-test",
                "api_key": "sk-user-secret-1234567890",
                "api_format": "chat_completions",
                "is_default": True,
            },
        )

        mine = list_user_providers(self.user.id)
        other = list_user_providers(self.other.id)
        active = get_active_config_for_user(self.user.id)

        self.assertEqual(created["provider_id"], "personal-openai")
        self.assertEqual(len(mine), 1)
        self.assertEqual(other, [])
        self.assertTrue(mine[0]["has_key"])
        self.assertNotIn("sk-user-secret", str(mine[0]))
        self.assertEqual(active["provider_id"], "personal-openai")
        self.assertEqual(active["model_id"], "gpt-test")
        self.assertEqual(active["api_key"], "sk-user-secret-1234567890")
        self.assertEqual(get_active_config_for_user(self.other.id)["provider_id"], "opencode-zen-free")

    def test_user_provider_routes_create_list_and_activate_current_user_only(self):
        token = create_access_token(self.user.id, self.user.username)
        other_token = create_access_token(self.other.id, self.other.username)
        client = TestClient(app)

        create_response = client.post(
            "/api/v1/providers/user",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "provider_id": "personal-local",
                "display_name": "Local",
                "base_url": "http://localhost:11434/v1",
                "model": "llama-test",
                "api_key": "local-secret",
                "api_format": "chat_completions",
                "is_default": False,
            },
        )
        data = create_response.json()
        activate_response = client.post(
            f"/api/v1/providers/user/{data['id']}/activate",
            headers={"Authorization": f"Bearer {token}"},
        )
        list_response = client.get("/api/v1/providers/user", headers={"Authorization": f"Bearer {token}"})
        other_list_response = client.get("/api/v1/providers/user", headers={"Authorization": f"Bearer {other_token}"})
        active_response = client.get("/api/v1/providers/active-config", headers={"Authorization": f"Bearer {token}"})
        global_response = client.post(
            "/api/v1/providers/user/use-global",
            headers={"Authorization": f"Bearer {token}"},
        )
        active_global_response = client.get(
            "/api/v1/providers/active-config",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(activate_response.status_code, 200)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(other_list_response.status_code, 200)
        self.assertEqual(active_response.status_code, 200)
        self.assertEqual(global_response.status_code, 200)
        self.assertEqual(len(list_response.json()["providers"]), 1)
        self.assertEqual(other_list_response.json()["providers"], [])
        self.assertNotIn("local-secret", str(list_response.json()))
        self.assertEqual(active_response.json()["provider_id"], "personal-local")
        self.assertTrue(active_response.json()["has_key"])
        self.assertNotEqual(active_global_response.json()["provider_id"], "personal-local")

    def test_non_admin_can_export_and_import_personal_provider_bundle(self):
        from src.core.user_provider_manager import create_user_provider, get_active_config_for_user

        token = create_access_token(self.user.id, self.user.username)
        other_token = create_access_token(self.other.id, self.other.username)
        client = TestClient(app)
        create_user_provider(
            self.user.id,
            {
                "provider_id": "portable-morph",
                "display_name": "Morph pessoal",
                "base_url": "https://api.morphllm.com/v1",
                "model": "morph-dsv4flash",
                "api_key": "portable-secret",
                "is_default": True,
            },
        )

        with patch(
            "src.api.routes.pm_export_custom",
            return_value=[{
                "id": "global-custom",
                "name": "Global",
                "base_url": "https://global.example.test/v1",
                "api_format": "chat_completions",
                "models": [{"id": "global-model", "enabled": True}],
            }],
        ) as export_custom:
            exported = client.get(
                "/api/v1/providers/export?include_api_keys=true",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(exported.status_code, 200)
        bundle = exported.json()
        self.assertEqual(bundle["personal_providers"][0]["api_key"], "portable-secret")
        self.assertFalse(bundle["custom_api_keys_included"])
        export_custom.assert_called_once_with(include_api_keys=False)

        imported = client.post(
            "/api/v1/providers/import",
            headers={"Authorization": f"Bearer {other_token}"},
            json=bundle,
        )

        self.assertEqual(imported.status_code, 200)
        self.assertEqual(
            imported.json()["personal"]["created"],
            ["portable-morph", "global-custom"],
        )
        self.assertEqual(
            imported.json()["custom"]["converted_to_personal"],
            [{"id": "global-custom", "model": "global-model"}],
        )
        self.assertEqual(get_active_config_for_user(self.other.id)["api_key"], "portable-secret")

    def test_admin_backup_and_codex_pool_are_forbidden_to_regular_users(self):
        token = create_access_token(self.user.id, self.user.username)
        client = TestClient(app)

        backup = client.get(
            "/api/v1/providers/admin-backup",
            headers={"Authorization": f"Bearer {token}"},
        )
        codex = client.get(
            "/api/v1/codex/pool/codex-chatgpt",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(backup.status_code, 403)
        self.assertEqual(codex.status_code, 403)

    def test_admin_backup_contains_provider_codex_and_antigravity_credentials(self):
        from src.db.models import User, get_session_db

        db = get_session_db()
        try:
            row = db.query(User).filter(User.id == self.user.id).first()
            row.is_admin = True
            db.commit()
        finally:
            db.close()
        token = create_access_token(self.user.id, self.user.username)
        client = TestClient(app)

        with (
            patch("src.api.routes.pm_export_complete_state", return_value={"provider_keys": {"x": "secret"}}),
            patch("src.api.routes.export_user_providers", return_value=[{"api_key": "personal-secret"}]),
            patch("src.core.account_pool.export_accounts", return_value={"accounts": [{"access_token": "codex-token"}]}),
            patch("src.core.antigravity_accounts.export_accounts", return_value={"accounts": [{"access_token": "ag-token"}]}),
        ):
            response = client.get(
                "/api/v1/providers/admin-backup",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["format"], "chatbot-admin-complete-backup")
        self.assertEqual(body["provider_state"]["provider_keys"]["x"], "secret")
        self.assertEqual(body["codex_auth"]["accounts"][0]["access_token"], "codex-token")
        self.assertEqual(body["antigravity_auth"]["accounts"][0]["access_token"], "ag-token")

    def test_chat_route_passes_active_user_provider_to_chat_engine(self):
        from src.core.user_provider_manager import create_user_provider

        token = create_access_token(self.user.id, self.user.username)
        client = TestClient(app)
        seen = []

        class FakeChatEngine:
            def __init__(
                self,
                memory,
                provider_config=None,
                response_mode="normal",
                reasoning_effort=None,
            ):
                seen.append(provider_config)

            async def chat_stream(self, message):
                yield "content", "ok"

        create_user_provider(
            self.user.id,
            {
                "provider_id": "personal-chat",
                "display_name": "Chat Personal",
                "base_url": "https://chat.example.test/v1",
                "model": "chat-user-model",
                "api_key": "chat-secret",
                "is_default": True,
            },
        )

        with patch("src.api.routes.ChatEngine", new=FakeChatEngine):
            response = client.post(
                "/api/v1/chat",
                headers={"Authorization": f"Bearer {token}"},
                json={"message": "oi", "session_id": "provider-hotpath"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen[0]["provider_id"], "personal-chat")
        self.assertEqual(seen[0]["model_id"], "chat-user-model")
        self.assertEqual(response.json()["provider_id"], "personal-chat")

    def test_provider_test_without_body_uses_active_user_provider(self):
        from src.core.user_provider_manager import create_user_provider

        token = create_access_token(self.user.id, self.user.username)
        client = TestClient(app)

        create_user_provider(
            self.user.id,
            {
                "provider_id": "personal-test",
                "display_name": "Personal Test",
                "base_url": "https://example.test/v1",
                "model": "personal-test-model",
                "api_key": "",
                "is_default": True,
            },
        )

        response = client.post(
            "/api/v1/providers/test",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ok"], False)
        self.assertEqual(response.json()["provider"], "personal-test")
        self.assertEqual(response.json()["model"], "personal-test-model")
        self.assertEqual(response.json()["error_type"], "no_key")

    def test_health_with_token_reports_active_user_provider(self):
        from src.core.user_provider_manager import create_user_provider

        token = create_access_token(self.user.id, self.user.username)
        client = TestClient(app)

        create_user_provider(
            self.user.id,
            {
                "provider_id": "personal-health",
                "display_name": "Personal Health",
                "base_url": "https://example.test/v1",
                "model": "personal-health-model",
                "api_key": "",
                "is_default": True,
            },
        )

        response = client.get("/api/v1/health", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "personal-health")
        self.assertEqual(response.json()["model"], "personal-health-model")


if __name__ == "__main__":
    unittest.main()
