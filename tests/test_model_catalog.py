import unittest
from unittest.mock import patch

from src.core.model_catalog import canonical_model_name, enrich_builtin_models


class ModelCatalogTests(unittest.TestCase):
    def test_enriches_reasoning_and_vision_from_models_dev(self):
        catalog = {
            "openai": {
                "models": {
                    "gpt-test": {
                        "reasoning": True,
                        "tool_call": True,
                        "modalities": {"input": ["text", "image", "pdf"]},
                    }
                }
            }
        }
        with patch("src.core.model_catalog.get_catalog", return_value=catalog):
            model = enrich_builtin_models("openai", [{"id": "gpt-test", "name": "GPT Test"}])[0]
        self.assertTrue(model["supports_thinking"])
        self.assertTrue(model["supports_images"])
        self.assertTrue(model["supports_pdf"])
        self.assertEqual(model["catalog_source"], "models.dev")

    def test_preserves_provider_specific_capabilities(self):
        catalog = {
            "openai": {
                "models": {
                    "gpt-test": {
                        "reasoning": True,
                        "modalities": {"input": ["text", "image"]},
                    }
                }
            }
        }
        with patch("src.core.model_catalog.get_catalog", return_value=catalog):
            model = enrich_builtin_models(
                "openai",
                [{"id": "gpt-test", "supports_images": False, "supports_thinking": False}],
            )[0]
        self.assertFalse(model["supports_images"])
        self.assertFalse(model["supports_thinking"])

    def test_uses_bundled_snapshot_when_catalog_is_offline(self):
        with patch("src.core.model_catalog.get_catalog", return_value={}):
            model = enrich_builtin_models("openai", [{"id": "gpt-5.4"}])[0]
        self.assertTrue(model["supports_images"])
        self.assertTrue(model["supports_thinking"])
        self.assertEqual(model["catalog_source"], "models.dev-snapshot")

    def test_repairs_antigravity_name_that_conflicts_with_model_id(self):
        self.assertEqual(
            canonical_model_name(
                "antigravity",
                "gemini-2.5-flash-thinking",
                "Gemini 3.1 Flash Lite",
            ),
            "Gemini 2.5 Flash Thinking",
        )

        model = enrich_builtin_models(
            "antigravity",
            [{"id": "gemini-2.5-flash", "name": "Gemini 3.1 Flash Lite"}],
        )[0]
        self.assertEqual(model["name"], "Gemini 2.5 Flash")

    def test_applies_verified_provider_specific_capability_override(self):
        with patch("src.core.model_catalog.get_catalog", return_value={}):
            model = enrich_builtin_models(
                "cerebras",
                [{"id": "gemma-4-31b", "supports_thinking": True}],
            )[0]
        self.assertFalse(model["supports_thinking"])


if __name__ == "__main__":
    unittest.main()
