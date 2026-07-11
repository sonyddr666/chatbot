import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendStreamingUiTest(unittest.TestCase):
    def test_http_stream_sends_response_mode_and_displays_status(self):
        api = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")
        store = (ROOT / "frontend/src/hooks/useChatStore.ts").read_text(encoding="utf-8")
        message = (ROOT / "frontend/src/components/ChatMessage.tsx").read_text(encoding="utf-8")

        self.assertIn("response_mode: responseMode", api)
        self.assertIn("'normal' | 'thinking' | 'live'", api)
        self.assertIn("streamStatus: chunk.text || 'Processando...'", store)
        self.assertIn("status || 'Aguardando o primeiro token...'", message)

    def test_reasoning_remains_visible_while_content_streams(self):
        app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
        message = (ROOT / "frontend/src/components/ChatMessage.tsx").read_text(encoding="utf-8")

        self.assertIn("const hasReasoning = !!message.reasoning", message)
        self.assertIn("msg.id === messages[messages.length - 1]?.id", app)
        self.assertIn("onStatus: status =>", app)

    def test_completed_skill_activity_is_visible_with_source_links(self):
        api = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")
        app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
        block = (ROOT / "frontend/src/components/SkillActivityBlock.tsx").read_text(encoding="utf-8")

        self.assertIn("type: 'skill_activity'", api)
        self.assertIn("chunk.type === 'skill_activity'", app)
        self.assertIn("Ferramentas e Skills", block)
        self.assertIn("fontes verificadas", block)
        self.assertIn('target="_blank"', block)

    def test_input_remains_editable_while_model_is_busy(self):
        app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
        chat_input = (ROOT / "frontend/src/components/ChatInput.tsx").read_text(encoding="utf-8")

        self.assertIn("busy={isLoading}", app)
        self.assertNotIn("disabled={busy}", chat_input)
        self.assertIn("Continue digitando", chat_input)
        self.assertIn("disabled={busy || !input.trim()}", chat_input)

    def test_saved_trace_is_restored_when_conversation_reopens(self):
        store = (ROOT / "frontend/src/hooks/useChatStore.ts").read_text(encoding="utf-8")

        self.assertIn("reasoning: m.reasoning || ''", store)
        self.assertIn("skillActivities: Array.isArray(m.skill_activities)", store)


if __name__ == "__main__":
    unittest.main()
