import unittest
from pathlib import Path


class FrontendStateSynchronizationTest(unittest.TestCase):
    def test_provider_selection_rejects_stale_responses_and_notifies_consumers(self):
        selector = Path("frontend/src/components/ModelSelector.tsx").read_text(encoding="utf-8")
        manager = Path("frontend/src/components/ProviderManager.tsx").read_text(encoding="utf-8")

        self.assertIn("providersRequestRef", selector)
        self.assertIn("/providers/manage?compact=true", selector)
        self.assertIn("sessionStorage.setItem(`${PROVIDERS_CACHE_KEY}:${owner}`", selector)
        self.assertNotIn("apiFetch(`${API}/providers/manage`, { signal:", selector)
        self.assertIn("await loadConfig()", selector)
        self.assertIn("syncChatProvider", manager)
        self.assertIn("new CustomEvent('provider-changed')", manager)

    def test_catalog_provider_setup_only_requests_key_and_keeps_models_hidden_until_tested(self):
        manager = Path("frontend/src/components/ProviderManager.tsx").read_text(encoding="utf-8")

        self.assertIn("catalogQuickSetup", manager)
        self.assertIn("catalogProvider.quick_setup ? catalogProvider : null", manager)
        self.assertIn("enabled: false, active: false", manager)
        self.assertIn("formApiKey", manager)
        self.assertIn("teste e habilite somente", manager)

    def test_shared_store_loaders_ignore_outdated_user_responses(self):
        store = Path("frontend/src/hooks/useChatStore.ts").read_text(encoding="utf-8")

        for sequence in (
            "conversationsLoadSequence",
            "configLoadSequence",
            "profilesLoadSequence",
            "documentsLoadSequence",
            "statsLoadSequence",
        ):
            self.assertIn(sequence, store)
        self.assertIn("owner === pendingOwner()", store)

    def test_rag_choice_is_persistent_and_not_reset_by_provider_refresh(self):
        store = Path("frontend/src/hooks/useChatStore.ts").read_text(encoding="utf-8")
        settings = Path("frontend/src/components/SettingsPanel.tsx").read_text(encoding="utf-8")

        self.assertIn("chatbot_use_rag", store)
        self.assertNotIn("setUseRag(config.rag)", settings)

    def test_sidebar_document_changes_are_broadcast(self):
        sidebar = Path("frontend/src/components/Sidebar.tsx").read_text(encoding="utf-8")

        self.assertGreaterEqual(sidebar.count("new CustomEvent('documents-changed')"), 2)


if __name__ == "__main__":
    unittest.main()
