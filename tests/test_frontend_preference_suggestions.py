import unittest
from pathlib import Path


class FrontendPreferenceSuggestionsTest(unittest.TestCase):
    def test_frontend_exposes_preference_suggestion_api_and_settings_ui(self):
        api_ts = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")
        settings_panel = Path("frontend/src/components/SettingsPanel.tsx").read_text(encoding="utf-8")

        self.assertIn("PreferenceSuggestionInfo", api_ts)
        self.assertIn("listPreferenceSuggestions", api_ts)
        self.assertIn("resolvePreferenceSuggestion", api_ts)
        self.assertIn("/preference-suggestions", api_ts)

        self.assertIn("Sugestoes inteligentes", settings_panel)
        self.assertIn("Aceitar", settings_panel)
        self.assertIn("Rejeitar", settings_panel)


if __name__ == "__main__":
    unittest.main()
