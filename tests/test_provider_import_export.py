import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core import provider_manager


class ProviderImportExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.data_dir = Path(self.tmp.name)
        self.providers_file = self.data_dir / "providers.json"
        self.patches = [
            patch.object(provider_manager, "DATA_DIR", str(self.data_dir)),
            patch.object(provider_manager, "PROVIDERS_FILE", str(self.providers_file)),
        ]
        for current in self.patches:
            current.start()

    def tearDown(self):
        for current in reversed(self.patches):
            current.stop()
        self.tmp.cleanup()

    def _seed(self):
        provider_manager._save_raw({
            "custom_providers": [
                {
                    "id": "morph",
                    "name": "Morph",
                    "base_url": "https://api.morphllm.com/v1",
                    "endpoint": "",
                    "api_key": "",
                    "api_format": "chat_completions",
                    "enabled": True,
                    "models": [
                        {
                            "id": "morph-dsv4flash",
                            "name": "DeepSeek V4 Flash",
                            "context_length": 1000000,
                            "enabled": True,
                            "api_key": "nested-secret",
                        }
                    ],
                },
                {
                    "id": "my-gateway",
                    "name": "My Gateway",
                    "base_url": "https://gateway.example.test/v1",
                    "endpoint": "",
                    "api_key": "",
                    "api_format": "chat_completions",
                    "enabled": True,
                    "models": [{
                        "id": "model-test",
                        "name": "Model Test",
                        "context_length": 128000,
                        "enabled": True,
                        "api_key": "nested-secret",
                    }],
                },
            ],
            "active_provider_id": "morph",
            "active_model_id": "morph-dsv4flash",
            "provider_keys": {"morph": "effective-secret", "my-gateway": "gateway-secret"},
            "builtin_provider_overrides": {},
            "builtin_model_overrides": {},
        })

    def test_export_can_omit_or_include_effective_api_key(self):
        self._seed()

        safe = provider_manager.export_custom_providers(include_api_keys=False)
        sensitive = provider_manager.export_custom_providers(include_api_keys=True)

        self.assertNotIn("api_key", safe[0])
        self.assertNotIn("effective-secret", str(safe))
        self.assertNotIn("nested-secret", str(safe))
        self.assertNotIn("nested-secret", str(sensitive))
        self.assertEqual([item["id"] for item in safe], ["my-gateway"])
        self.assertEqual(sensitive[0]["api_key"], "gateway-secret")

    def test_active_custom_provider_uses_key_saved_by_ui(self):
        self._seed()

        active = provider_manager.get_active_config()

        self.assertEqual(active["provider_id"], "morph")
        self.assertEqual(active["api_key"], "effective-secret")

    def test_promoted_provider_cannot_be_deleted_or_reconfigured(self):
        self._seed()

        self.assertFalse(provider_manager.delete_provider("morph"))
        with self.assertRaisesRegex(ValueError, "built-in"):
            provider_manager.update_provider("morph", {"base_url": "https://evil.example.test"})
        self.assertEqual(provider_manager.get_provider("morph")["base_url"], "https://api.morphllm.com/v1")

    def test_custom_provider_list_reports_effective_saved_key_without_exposing_it(self):
        self._seed()

        provider = next(item for item in provider_manager.list_providers() if item["id"] == "morph")

        self.assertTrue(provider["has_key"])
        self.assertEqual(provider["api_key"], "sk-...")
        self.assertEqual(provider["key_source"], "ui")
        self.assertNotIn("effective-secret", str(provider))
        self.assertEqual(provider["provider_type"], "builtin")
        self.assertEqual(provider["api_key_url"], "https://morphllm.com/dashboard/api-keys")
        self.assertTrue(provider["docs_url"].startswith("https://"))

    def test_import_does_not_overwrite_managed_builtin_providers(self):
        self._seed()

        result = provider_manager.import_custom_providers([
            {
                "id": "morph",
                "name": "Morph atualizado",
                "base_url": "https://api.morphllm.com/v1",
                "api_format": "chat_completions",
                "enabled": False,
                "api_key": "new-secret",
                "models": [
                    {
                        "id": "morph-glm52-744b",
                        "name": "GLM-5.2",
                        "context_length": 1000000,
                        "enabled": True,
                    }
                ],
            },
            {
                "id": "openrouter",
                "name": "OpenRouter",
                "base_url": "https://openrouter.ai/api/v1",
                "models": [],
            },
            {"id": "openai", "name": "Nao sobrescrever built-in"},
        ])

        raw = provider_manager._load_raw()
        morph = next(item for item in raw["custom_providers"] if item["id"] == "morph")
        self.assertEqual(result["created"], [])
        self.assertEqual(result["updated"], [])
        self.assertEqual([item["id"] for item in result["skipped"]], ["morph", "openrouter", "openai"])
        self.assertEqual(morph["name"], "Morph")
        self.assertTrue(morph["enabled"])
        self.assertEqual(morph["models"][0]["id"], "morph-dsv4flash")
        self.assertEqual(raw["provider_keys"]["morph"], "effective-secret")
        self.assertEqual(raw["active_provider_id"], "morph")

    def test_complete_state_round_trip_preserves_keys_overrides_and_active_selection(self):
        self._seed()
        exported = provider_manager.export_complete_state()
        provider_manager._save_raw(dict(provider_manager.DEFAULT_PROVIDERS_DATA))

        result = provider_manager.import_complete_state(exported)
        restored = provider_manager._load_raw()

        self.assertEqual(restored["provider_keys"]["morph"], "effective-secret")
        self.assertEqual(restored["active_provider_id"], "morph")
        self.assertEqual(restored["active_model_id"], "morph-dsv4flash")
        self.assertGreaterEqual(result["providers"], len(provider_manager.BUILTIN_PROVIDERS))
        # Inclui as duas chaves salvas e quaisquer credenciais efetivas vindas
        # do ambiente da instalacao que tornam o backup realmente portavel.
        self.assertGreaterEqual(result["keys"], 2)


if __name__ == "__main__":
    unittest.main()
