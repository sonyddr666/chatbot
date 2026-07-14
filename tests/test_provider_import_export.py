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
                    "api_key": "provider-copy",
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
                }
            ],
            "active_provider_id": "morph",
            "active_model_id": "morph-dsv4flash",
            "provider_keys": {"morph": "effective-secret"},
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
        self.assertEqual(sensitive[0]["api_key"], "effective-secret")

    def test_active_custom_provider_uses_key_saved_by_ui(self):
        self._seed()

        active = provider_manager.get_active_config()

        self.assertEqual(active["provider_id"], "morph")
        self.assertEqual(active["api_key"], "effective-secret")

    def test_import_merges_by_id_and_does_not_disable_active_provider(self):
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
        self.assertEqual(result["created"], ["openrouter"])
        self.assertEqual(result["updated"], ["morph"])
        self.assertEqual(result["skipped"][0]["id"], "openai")
        self.assertEqual(morph["name"], "Morph atualizado")
        self.assertTrue(morph["enabled"])
        self.assertEqual(morph["models"][0]["id"], "morph-glm52-744b")
        self.assertEqual(raw["provider_keys"]["morph"], "new-secret")
        self.assertEqual(raw["active_provider_id"], "morph")


if __name__ == "__main__":
    unittest.main()
