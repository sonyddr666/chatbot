import unittest
from pathlib import Path


class FrontendUserProvidersTest(unittest.TestCase):
    def test_frontend_exposes_personal_provider_api_and_ui(self):
        api_ts = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")
        provider_manager = Path("frontend/src/components/ProviderManager.tsx").read_text(encoding="utf-8")

        self.assertIn("UserProviderInfo", api_ts)
        self.assertIn("listUserProviders", api_ts)
        self.assertIn("createUserProvider", api_ts)
        self.assertIn("activateUserProvider", api_ts)
        self.assertIn("/providers/user", api_ts)

        self.assertIn("Providers pessoais", provider_manager)
        self.assertIn("Criar provider pessoal", provider_manager)
        self.assertIn("Ativar pessoal", provider_manager)


if __name__ == "__main__":
    unittest.main()
