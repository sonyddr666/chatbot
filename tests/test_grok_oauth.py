import time
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage, SystemMessage

from src.core import grok_oauth
from src.core.grok_client import _event_parts, _payload, request_headers


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload


class FakeAsyncClient:
    responses = []
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)


class GrokOAuthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        grok_oauth._device_sessions.clear()
        grok_oauth._refresh_locks.clear()
        grok_oauth._discovery_cache = None
        FakeAsyncClient.responses = []
        FakeAsyncClient.calls = []

    def test_secret_encryption_roundtrip_and_tamper_detection(self):
        encrypted = grok_oauth.encrypt_secret("token-super-secreto")
        self.assertNotIn("token-super-secreto", encrypted)
        self.assertEqual(grok_oauth.decrypt_secret(encrypted), "token-super-secreto")
        self.assertEqual(grok_oauth.decrypt_secret(encrypted[:-2] + "xx"), "")

    async def test_device_start_keeps_device_code_on_backend(self):
        FakeAsyncClient.responses = [
            FakeResponse(payload={
                "issuer": grok_oauth.ISSUER,
                "device_authorization_endpoint": "https://auth.x.ai/oauth2/device/code",
                "token_endpoint": "https://auth.x.ai/oauth2/token",
                "userinfo_endpoint": "https://auth.x.ai/oauth2/userinfo",
            }),
            FakeResponse(payload={
                "device_code": "server-only-device-code",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://auth.x.ai/device",
                "expires_in": 600,
                "interval": 5,
            }),
        ]
        with patch("src.core.grok_oauth.httpx.AsyncClient", FakeAsyncClient):
            result = await grok_oauth.start_device_oauth(7)

        self.assertEqual(result["user_code"], "ABCD-EFGH")
        self.assertNotIn("device_code", result)
        self.assertEqual(grok_oauth._device_sessions[result["request_id"]]["device_code"], "server-only-device-code")
        post_data = FakeAsyncClient.calls[1][2]["data"]
        self.assertEqual(post_data["client_id"], grok_oauth.CLIENT_ID)
        self.assertIn("offline_access", post_data["scope"])

    async def test_poll_handles_pending_slow_down_and_success(self):
        request_id = "grokoauth_test"
        grok_oauth._device_sessions[request_id] = {
            "user_id": 9,
            "device_code": "device",
            "token_endpoint": "https://auth.x.ai/oauth2/token",
            "userinfo_endpoint": "https://auth.x.ai/oauth2/userinfo",
            "expires_at": time.time() + 600,
            "interval": 3,
            "next_poll_at": 0,
        }
        FakeAsyncClient.responses = [FakeResponse(400, {"error": "authorization_pending"})]
        with patch("src.core.grok_oauth.httpx.AsyncClient", FakeAsyncClient):
            pending = await grok_oauth.poll_device_oauth(9, request_id)
        self.assertEqual(pending["status"], "pending")

        grok_oauth._device_sessions[request_id]["next_poll_at"] = 0
        FakeAsyncClient.responses = [FakeResponse(400, {"error": "slow_down"})]
        with patch("src.core.grok_oauth.httpx.AsyncClient", FakeAsyncClient):
            slowed = await grok_oauth.poll_device_oauth(9, request_id)
        self.assertEqual(slowed["retry_after"], 8)

        grok_oauth._device_sessions[request_id]["next_poll_at"] = 0
        FakeAsyncClient.responses = [
            FakeResponse(200, {"access_token": "access", "refresh_token": "refresh", "expires_in": 3600}),
            FakeResponse(200, {"sub": "subject-1", "email": "user@example.com", "name": "User"}),
        ]
        with patch("src.core.grok_oauth.httpx.AsyncClient", FakeAsyncClient), patch(
            "src.core.grok_oauth.save_account", return_value={"id": "grok_1"}
        ) as save:
            saved = await grok_oauth.poll_device_oauth(9, request_id)
        self.assertEqual(saved["status"], "saved")
        self.assertNotIn(request_id, grok_oauth._device_sessions)
        self.assertEqual(save.call_args.args[2]["sub"], "subject-1")

    async def test_refresh_persists_rotated_refresh_token(self):
        old_account = {
            "id": "grok_1",
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_at": 0,
            "scope": grok_oauth.SCOPES,
        }
        refreshed = {**old_account, "access_token": "new-access", "refresh_token": "new-refresh"}
        FakeAsyncClient.responses = [FakeResponse(200, {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        })]
        with patch("src.core.grok_oauth.get_account", side_effect=[old_account, refreshed]), patch(
            "src.core.grok_oauth.discovery", return_value={"token_endpoint": "https://auth.x.ai/oauth2/token"}
        ), patch("src.core.grok_oauth.httpx.AsyncClient", FakeAsyncClient), patch(
            "src.core.grok_oauth.update_account"
        ) as update:
            result = await grok_oauth.refresh_access_token(1, "grok_1", force=True)

        self.assertEqual(result["access_token"], "new-access")
        persisted = update.call_args.args[2]
        self.assertEqual(persisted["access_token"], "new-access")
        self.assertEqual(persisted["refresh_token"], "new-refresh")
        self.assertNotIn("client_secret", FakeAsyncClient.calls[0][2]["data"])

    def test_responses_payload_and_events(self):
        payload = _payload(
            [SystemMessage(content="Seja direto"), HumanMessage(content="Oi")],
            "grok-4.5",
            "high",
        )
        self.assertEqual(payload["instructions"], "Seja direto")
        self.assertEqual(payload["input"][0], {"role": "user", "content": "Oi"})
        self.assertEqual(payload["reasoning"], {"effort": "high"})
        self.assertEqual(
            _event_parts({"type": "response.output_text.delta", "delta": "ola"}),
            [("content", "ola")],
        )
        self.assertEqual(
            _event_parts({"type": "response.reasoning_summary_text.delta", "delta": "pensando"}),
            [("reasoning", "pensando")],
        )

    def test_subscription_proxy_headers_match_grok_build(self):
        headers = request_headers(
            {"access_token": "secret", "subject": "user-1"},
            "grok-4.5",
        )
        self.assertEqual(grok_oauth.OAUTH_API_BASE, "https://cli-chat-proxy.grok.com/v1")
        self.assertEqual(headers["x-grok-client-identifier"], "grok-shell")
        self.assertEqual(headers["x-grok-client-version"], grok_oauth.GROK_CLIENT_VERSION)
        self.assertEqual(headers["x-grok-model-override"], "grok-4.5")
        self.assertEqual(headers["x-grok-user-id"], "user-1")
        self.assertTrue(headers["x-grok-conv-id"])
        self.assertTrue(headers["x-grok-req-id"])


if __name__ == "__main__":
    unittest.main()
