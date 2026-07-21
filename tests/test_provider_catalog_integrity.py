import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from src.core import provider_manager


class ProviderCatalogIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.data_dir = Path(self.tmp.name)
        self.providers_file = self.data_dir / "providers.json"
        self.patches = [
            patch.object(provider_manager, "DATA_DIR", str(self.data_dir)),
            patch.object(provider_manager, "PROVIDERS_FILE", str(self.providers_file)),
            patch("src.core.model_catalog.get_catalog", return_value={"google": {"models": {}}}),
            patch(
                "src.core.model_catalog.list_catalog_models",
                return_value=[{
                    "id": "gemini-test",
                    "name": "Gemini Test",
                    "context_length": 128000,
                    "catalog_source": "models.dev",
                    "catalog_provider_id": "google",
                }],
            ),
        ]
        for current in self.patches:
            current.start()

    def tearDown(self):
        for current in reversed(self.patches):
            current.stop()
        self.tmp.cleanup()

    def _seed_google(self, models):
        state = deepcopy(provider_manager.DEFAULT_PROVIDERS_DATA)
        state["custom_providers"] = [{
            "id": "google",
            "name": "Google",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "api_format": "chat_completions",
            "enabled": True,
            "catalog_provider_id": "google",
            "models": models,
        }]
        provider_manager._save_raw(state)

    def test_catalog_backed_creation_ignores_models_from_another_provider(self):
        created = provider_manager.create_provider({
            "id": "google",
            "name": "Google",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "api_format": "chat_completions",
            "catalog_provider_id": "google",
            "models": [{
                "id": "claude-from-abacus",
                "name": "Claude from Abacus",
                "context_length": 200000,
                "enabled": False,
                "catalog_source": "models.dev",
                "catalog_provider_id": "abacus",
            }],
        })

        self.assertEqual([model["id"] for model in created["models"]], ["gemini-test"])
        self.assertEqual(created["models"][0]["catalog_provider_id"], "google")
        self.assertFalse(created["models"][0]["enabled"])

    def test_sync_removes_foreign_hidden_models_but_preserves_manual_models(self):
        self._seed_google([
            {
                "id": "gemini-test",
                "name": "Old Gemini Name",
                "context_length": 64000,
                "enabled": True,
                "catalog_source": "models.dev",
                "catalog_provider_id": "google",
            },
            {
                "id": "claude-from-legacy-race",
                "name": "Claude",
                "context_length": 200000,
                "enabled": False,
                "catalog_source": "models.dev",
            },
            {
                "id": "qwen-from-alibaba",
                "name": "Qwen",
                "context_length": 128000,
                "enabled": False,
                "catalog_source": "models.dev",
                "catalog_provider_id": "alibaba",
            },
            {
                "id": "retired-gemini",
                "name": "Retired Gemini",
                "context_length": 128000,
                "enabled": True,
                "catalog_source": "models.dev",
                "catalog_provider_id": "google",
            },
            {
                "id": "manual-proxy-model",
                "name": "Manual Proxy Model",
                "context_length": 128000,
                "enabled": False,
            },
        ])

        result = provider_manager.sync_models_from_catalog("google")
        ids = {model["id"] for model in result["models"]}

        self.assertEqual(ids, {"gemini-test", "retired-gemini", "manual-proxy-model"})
        self.assertEqual(result["removed_hidden"], 2)
        self.assertEqual(result["preserved_manual"], 1)
        retired = next(model for model in result["models"] if model["id"] == "retired-gemini")
        self.assertTrue(retired["catalog_removed"])

    def test_sync_rejects_switching_an_existing_provider_to_another_catalog(self):
        self._seed_google([])

        with self.assertRaisesRegex(ValueError, "nao corresponde"):
            provider_manager.sync_models_from_catalog("google", "abacus")

    def test_catalog_backed_import_is_reconciled_against_its_declared_source(self):
        result = provider_manager.import_custom_providers([{
            "id": "custom-google",
            "name": "Custom Google",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "catalog_provider_id": "google",
            "models": [{
                "id": "claude-from-abacus",
                "name": "Claude",
                "context_length": 200000,
                "enabled": False,
                "catalog_source": "models.dev",
            }],
        }])

        self.assertEqual(result["created"], ["custom-google"])
        stored = provider_manager._load_raw()["custom_providers"][0]
        self.assertEqual([model["id"] for model in stored["models"]], ["gemini-test"])
        self.assertEqual(stored["models"][0]["catalog_provider_id"], "google")

    def test_startup_repair_cleans_every_catalog_backed_custom_provider(self):
        self._seed_google([
            {
                "id": "claude-from-abacus",
                "name": "Claude",
                "context_length": 200000,
                "enabled": False,
                "catalog_source": "models.dev",
            },
            {
                "id": "manual-proxy-model",
                "name": "Manual Proxy Model",
                "context_length": 128000,
                "enabled": False,
            },
        ])

        result = provider_manager.repair_catalog_integrity()
        stored = provider_manager._load_raw()["custom_providers"][0]

        self.assertEqual(result["repaired"], ["google"])
        self.assertEqual(result["removed_catalog_models"], 1)
        self.assertEqual(
            {model["id"] for model in stored["models"]},
            {"gemini-test", "manual-proxy-model"},
        )

    def test_integrity_repair_replaces_an_active_foreign_catalog_model(self):
        self._seed_google([{
            "id": "claude-active-by-mistake",
            "name": "Claude Active",
            "context_length": 200000,
            "enabled": True,
            "catalog_source": "models.dev",
        }])
        state = provider_manager._load_raw()
        state["active_provider_id"] = "google"
        state["active_model_id"] = "claude-active-by-mistake"
        provider_manager._save_raw(state)

        provider_manager.repair_catalog_integrity()
        repaired = provider_manager._load_raw()
        stored = repaired["custom_providers"][0]

        self.assertNotIn("claude-active-by-mistake", {model["id"] for model in stored["models"]})
        self.assertEqual(repaired["active_model_id"], "gemini-test")
        self.assertTrue(stored["models"][0]["enabled"])

    def test_complete_state_restore_reconciles_catalog_backed_providers(self):
        state = deepcopy(provider_manager.DEFAULT_PROVIDERS_DATA)
        state["custom_providers"] = [{
            "id": "google",
            "name": "Google",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "catalog_provider_id": "google",
            "models": [{
                "id": "claude-from-backup",
                "name": "Claude",
                "enabled": False,
                "catalog_source": "models.dev",
            }],
        }]

        provider_manager.import_complete_state(state)
        stored = provider_manager._load_raw()["custom_providers"][0]

        self.assertEqual([model["id"] for model in stored["models"]], ["gemini-test"])


if __name__ == "__main__":
    unittest.main()
