import unittest
from unittest.mock import patch

from src.core.model_catalog import (
    canonical_model_name,
    enrich_builtin_models,
    list_catalog_models,
    list_catalog_providers,
)


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

    def test_lists_world_catalog_and_normalizes_models(self):
        catalog = {
            "anthropic": {
                "name": "Anthropic",
                "doc": "https://example.test/docs",
                "env": ["ANTHROPIC_API_KEY"],
                "models": {
                    "claude-test": {
                        "name": "Claude Test",
                        "family": "claude",
                        "reasoning": True,
                        "tool_call": True,
                        "limit": {"context": 200000, "output": 32000},
                        "modalities": {"input": ["text", "image", "pdf"]},
                        "last_updated": "2026-07-01",
                    }
                },
            }
        }
        with patch("src.core.model_catalog.get_catalog", return_value=catalog):
            providers = list_catalog_providers("anth")
            models = list_catalog_models("anthropic")
        self.assertEqual(providers[0]["model_count"], 1)
        self.assertEqual(models[0]["context_length"], 200000)
        self.assertEqual(models[0]["catalog_provider_id"], "anthropic")
        self.assertTrue(models[0]["supports_images"])
        self.assertTrue(models[0]["supports_pdf"])
        self.assertTrue(models[0]["supports_tools"])

    def test_world_provider_search_also_matches_models(self):
        catalog = {
            "xai": {
                "name": "xAI",
                "models": {
                    "grok-4.5": {"name": "Grok 4.5", "family": "grok"},
                },
            },
            "anthropic": {
                "name": "Anthropic",
                "models": {
                    "claude-test": {"name": "Claude Test", "family": "claude"},
                },
            },
        }
        with patch("src.core.model_catalog.get_catalog", return_value=catalog):
            providers = list_catalog_providers("grok")

        self.assertEqual([provider["id"] for provider in providers], ["xai"])
        self.assertIn("grok-4.5", providers[0]["model_search_index"])

    def test_catalog_exposes_ready_connection_defaults_for_aihubmix(self):
        catalog = {
            "aihubmix": {
                "name": "AIHubMix",
                "env": ["AIHUBMIX_API_KEY"],
                "models": {"working-model": {"name": "Working Model"}},
            }
        }
        with patch("src.core.model_catalog.get_catalog", return_value=catalog):
            provider = list_catalog_providers("aihubmix")[0]

        self.assertEqual(provider["api"], "https://aihubmix.com/v1")
        self.assertEqual(provider["api_format"], "chat_completions")
        self.assertTrue(provider["endpoint_verified"])
        self.assertTrue(provider["quick_setup"])

    def test_alibaba_pay_as_you_go_regions_accept_single_api_key_setup(self):
        catalog = {
            "alibaba": {
                "name": "Alibaba Cloud",
                "models": {"qwen-plus": {"name": "Qwen Plus"}},
            },
            "alibaba-cn": {
                "name": "Alibaba Cloud (China)",
                "models": {"qwen-plus": {"name": "Qwen Plus"}},
            },
        }

        with patch("src.core.model_catalog.get_catalog", return_value=catalog):
            providers = {
                provider["id"]: provider
                for provider in list_catalog_providers("alibaba")
            }

        self.assertEqual(providers["alibaba"]["required_fields"], ["api_key"])
        self.assertTrue(providers["alibaba"]["quick_setup"])
        self.assertEqual(providers["alibaba-cn"]["required_fields"], ["api_key"])
        self.assertTrue(providers["alibaba-cn"]["quick_setup"])

    def test_google_uses_documented_openai_compatibility_for_key_only_setup(self):
        catalog = {
            "google": {
                "name": "Google Gemini",
                "models": {"gemini-test": {"name": "Gemini Test"}},
            }
        }

        with patch("src.core.model_catalog.get_catalog", return_value=catalog):
            provider = list_catalog_providers("google")[0]

        self.assertEqual(
            provider["api"],
            "https://generativelanguage.googleapis.com/v1beta/openai",
        )
        self.assertEqual(provider["api_format"], "chat_completions")
        self.assertEqual(provider["auth_type"], "bearer_api_key")
        self.assertEqual(provider["required_fields"], ["api_key"])
        self.assertTrue(provider["quick_setup"])

    def test_unreviewed_provider_cannot_claim_key_only_quick_setup(self):
        catalog = {
            "unreviewed-example": {
                "name": "Unreviewed",
                "api": "https://example.test/v1",
                "env": ["EXAMPLE_API_KEY"],
                "models": {"model": {"name": "Model"}},
            }
        }
        with patch("src.core.model_catalog.get_catalog", return_value=catalog):
            provider = list_catalog_providers("unreviewed")[0]

        self.assertFalse(provider["endpoint_verified"])
        self.assertFalse(provider["quick_setup"])


if __name__ == "__main__":
    unittest.main()
