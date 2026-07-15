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
        self.assertIn("Exportar sem API keys", provider_manager)
        self.assertIn("Exportar com API keys", provider_manager)
        self.assertIn("Importar JSON", provider_manager)
        self.assertIn("/providers/export", provider_manager)
        self.assertIn("/providers/import", provider_manager)
        self.assertIn("setLocalApiKey('')", provider_manager)
        self.assertNotIn("setLocalApiKey(selected.has_key ? (selected.api_key || '') : '')", provider_manager)

    def test_app_starts_with_a_new_empty_chat_instead_of_default_history(self):
        app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

        self.assertIn("sessionId: `chat-${Date.now()}`", app)
        self.assertIn("initializedChatUserRef", app)
        self.assertNotIn("setSession(useChatStore.getState().sessionId)", app)
        self.assertIn('<UserRound size={14}', app)
        self.assertIn('<Brain size={14}', app)


if __name__ == "__main__":
    unittest.main()
