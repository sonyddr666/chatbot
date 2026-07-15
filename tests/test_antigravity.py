import unittest

from src.core.antigravity_accounts import decrypt_secret, encrypt_secret
from src.core.antigravity_client import _resolve_model, provider_models_from_account
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

    def test_image_action_is_conservative(self):
        image = [{"kind": "image", "id": "att_1"}]
        self.assertEqual(detect_image_action("melhore esta foto", image)["operation"], "edit")
        self.assertEqual(detect_image_action("crie uma imagem de uma cidade", [])["operation"], "generate")
        self.assertEqual(detect_image_action("crie 4 imagens de uma cidade", [])["count"], 4)
        self.assertIsNone(detect_image_action("o que tem nesta foto?", image))
        self.assertIsNone(detect_image_action("melhore este texto", []))

    def test_follow_up_can_reference_latest_image(self):
        self.assertTrue(references_previous_image("melhore essa imagem de novo"))
        self.assertFalse(references_previous_image("melhore esse paragrafo"))


if __name__ == "__main__":
    unittest.main()
