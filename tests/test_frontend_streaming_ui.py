import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendStreamingUiTest(unittest.TestCase):
    def test_http_stream_sends_thinking_preference_and_displays_status(self):
        api = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")
        store = (ROOT / "frontend/src/hooks/useChatStore.ts").read_text(encoding="utf-8")
        message = (ROOT / "frontend/src/components/ChatMessage.tsx").read_text(encoding="utf-8")

        self.assertIn("use_thinking: useThinking", api)
        self.assertIn("streamStatus: chunk.text || 'Processando...'", store)
        self.assertIn("status || 'Aguardando o primeiro token...'", message)

    def test_reasoning_remains_visible_while_content_streams(self):
        app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
        message = (ROOT / "frontend/src/components/ChatMessage.tsx").read_text(encoding="utf-8")

        self.assertIn("const hasReasoning = !!message.reasoning", message)
        self.assertIn("msg.id === messages[messages.length - 1]?.id", app)
        self.assertIn("onStatus: status =>", app)


if __name__ == "__main__":
    unittest.main()
