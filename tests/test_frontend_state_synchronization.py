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
        self.assertIn("catalogProvider.configuration_supported ? catalogProvider : null", manager)
        self.assertIn("auth_type: catalogBinding?.provider.auth_type || undefined", manager)
        self.assertNotIn("Configuracao rapida bloqueada", manager)
        self.assertIn("enabled: false, active: false", manager)
        self.assertIn("formApiKey", manager)
        self.assertIn("teste e habilite somente", manager)

    def test_catalog_provider_state_rejects_stale_models_and_clears_cross_selection(self):
        manager = Path("frontend/src/components/ProviderManager.tsx").read_text(encoding="utf-8")

        self.assertIn("catalogModelsRequestRef", manager)
        self.assertIn("data.provider_id !== provider.id", manager)
        self.assertIn("data.models.some(model => model.catalog_provider_id !== provider.id)", manager)
        self.assertIn("formCatalogModels", manager)
        self.assertIn("const firstModel = providerModels[0]", manager)
        self.assertIn("clearCatalogSelection", manager)
        self.assertIn("onClick={() => selectManagedProvider(p.id)}", manager)
        self.assertIn("providerView === 'catalog' && selectedCatalog", manager)

    def test_catalog_sidebar_search_cannot_match_models_from_another_provider(self):
        manager = Path("frontend/src/components/ProviderManager.tsx").read_text(encoding="utf-8")

        self.assertIn("catalogProviderSearchRank", manager)
        self.assertIn("const exactProviderMatch", manager)
        self.assertIn("const target = exactProviderMatch || selectedStillVisible", manager)
        self.assertIn('placeholder="Buscar provider..."', manager)
        self.assertNotIn("provider.model_search_index?.includes(normalizedCatalogSearch)", manager)

    def test_catalog_setup_form_cannot_be_closed_by_previous_search_selection(self):
        manager = Path("frontend/src/components/ProviderManager.tsx").read_text(encoding="utf-8")

        self.assertIn("catalogAutoSelectionSuppressedRef", manager)
        self.assertIn("if (catalogAutoSelectionSuppressedRef.current) return", manager)
        self.assertIn("catalogAutoSelectionSuppressedRef.current = true", manager)
        self.assertIn("catalogSetupBindingRef", manager)
        self.assertIn("catalogSetupBindingRef.current = { provider: catalogProvider, models: providerModels }", manager)
        self.assertIn("(catalogBinding?.models || []).map", manager)
        self.assertIn("catalogAutoSelectionSuppressedRef.current = false", manager)
        self.assertIn("catalogProvider.configuration_supported ? catalogProvider : null", manager)
        self.assertIn("catalogProvider.setup_message", manager)
        self.assertNotIn("Este provider exige configuracao adicional ou um adaptador especifico", manager)

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
