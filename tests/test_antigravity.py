import unittest

from src.core.antigravity_accounts import decrypt_secret, encrypt_secret
from src.core.antigravity_client import _reasoning_chunks, _resolve_model, provider_models_from_account
from src.core.image_actions import detect_image_action, references_previous_image


class AntigravityAdapterTests(unittest.TestCase):
    def test_oauth_secrets_round_trip_without_plaintext_storage(self):
        encrypted = encrypt_secret("access-token-example")
        self.assertNotIn("access-token-example", encrypted)
        self.assertEqual(decrypt_secret(encrypted), "access-token-example")

    def test_resolve_chat_and_image_models_separately(self):
        account = {
            "models": {
                "gemini-chat": {"displayName": "Gemini Chat", "recommended": True},
                "gemini-image": {"displayName": "Gemini Image"},
            }
        }
        self.assertEqual(_resolve_model(account, "gemini-chat", image=False)[0], "gemini-chat")
        self.assertEqual(_resolve_model(account, "gemini-chat", image=True)[0], "gemini-image")

    def test_catalog_preserves_capabilities(self):
        account = {
            "models": {
                "gemini-vision": {
                    "displayName": "Gemini Vision",
                    "supportsThinking": True,
                    "supportsImages": True,
                    "recommended": True,
                }
            }
        }
        model = provider_models_from_account(account)[0]
        self.assertTrue(model["supports_thinking"])
        self.assertTrue(model["supports_images"])
        self.assertTrue(model["recommended"])

    def test_extra_low_thinking_is_marked_internal_only(self):
        account = {
            "models": {
                "gemini-3.5-flash-extra-low": {
                    "displayName": "Gemini 3.5 Flash (Low)",
                    "supportsThinking": True,
                },
                "gemini-3.5-flash-low": {
                    "displayName": "Gemini 3.5 Flash (Medium)",
                    "supportsThinking": True,
                },
            }
        }
        models = {model["id"]: model for model in provider_models_from_account(account)}
        self.assertFalse(models["gemini-3.5-flash-extra-low"]["thinking_stream"])
        self.assertTrue(models["gemini-3.5-flash-low"]["thinking_stream"])

    def test_batched_reasoning_is_split_without_changing_text(self):
        original = "raciocinio enviado em um unico lote"
        chunks = _reasoning_chunks(original, size=7)
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), original)
        self.assertTrue(all(len(chunk) <= 7 for chunk in chunks))

    def test_image_action_is_conservative(self):
        image = [{"kind": "image", "id": "att_1"}]
        self.assertEqual(detect_image_action("melhore esta foto", image)["operation"], "edit")
        self.assertEqual(detect_image_action("crie uma imagem de uma cidade", [])["operation"], "generate")
        self.assertEqual(detect_image_action("gera uma imagem de um pato", [])["operation"], "generate")
        self.assertEqual(detect_image_action("gere um rato em cima da cama", [])["operation"], "generate")
        self.assertIsNone(detect_image_action("crie um relatorio sobre vendas", []))
        self.assertEqual(detect_image_action("gera um papel de parede com essa data", [])["operation"], "generate")
        self.assertEqual(detect_image_action("gera um papel e paree com essa data", [])["operation"], "generate")
        self.assertEqual(detect_image_action("crie 4 imagens de uma cidade", [])["count"], 4)
        self.assertIsNone(detect_image_action("o que tem nesta foto?", image))
        self.assertIsNone(detect_image_action("melhore este texto", []))
        self.assertIsNone(detect_image_action(
            "qual sua opiniao sobre isso: a regra deveria entender quando alguem diz crie uma imagem",
            [],
        ))
        self.assertIsNone(detect_image_action(
            "avalie este texto colado\n\n```text\ncrie uma imagem de uma cidade\n```",
            [],
        ))

    def test_follow_up_can_reference_latest_image(self):
        self.assertTrue(references_previous_image("melhore essa imagem de novo"))
        self.assertFalse(references_previous_image("melhore esse paragrafo"))


if __name__ == "__main__":
    unittest.main()
