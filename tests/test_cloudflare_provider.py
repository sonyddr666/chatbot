import unittest
from unittest.mock import patch

import httpx

from src.core.cloudflare_provider import discover_cloudflare_accounts, workers_ai_base_url


class CloudflareProviderTest(unittest.IsolatedAsyncioTestCase):
    def test_workers_ai_base_url_uses_valid_account_id(self):
        self.assertEqual(
            workers_ai_base_url("a1b2c3d4"),
            "https://api.cloudflare.com/client/v4/accounts/a1b2c3d4/ai/v1",
        )
        with self.assertRaises(ValueError):
            workers_ai_base_url("COLOQUE_SEU_ACCOUNT_ID")

    async def test_discovers_accounts_without_exposing_token(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["authorization"] = request.headers.get("authorization")
            return httpx.Response(200, json={
                "success": True,
                "result": [
                    {"id": "a1b2c3d4", "name": "Pessoal"},
                    {"id": "deadbeef", "name": "Empresa"},
                ],
            })

        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return real_client(*args, **kwargs)

        with patch("src.core.cloudflare_provider.httpx.AsyncClient", new=factory):
            accounts = await discover_cloudflare_accounts("secret-token")

        self.assertEqual(seen["authorization"], "Bearer secret-token")
        self.assertEqual(accounts, [
            {"id": "a1b2c3d4", "name": "Pessoal"},
            {"id": "deadbeef", "name": "Empresa"},
        ])

    async def test_permission_error_is_actionable(self):
        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(lambda request: httpx.Response(403, json={
            "success": False,
            "errors": [{"message": "Authentication error"}],
        }))

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return real_client(*args, **kwargs)

        with patch("src.core.cloudflare_provider.httpx.AsyncClient", new=factory):
            with self.assertRaisesRegex(RuntimeError, "Account Settings: Read"):
                await discover_cloudflare_accounts("limited-token")


if __name__ == "__main__":
    unittest.main()
