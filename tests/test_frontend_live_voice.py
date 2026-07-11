import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendLiveVoiceTest(unittest.TestCase):
    def test_live_voice_has_continuous_stt_endpointing_and_resume(self):
        hook = (ROOT / "frontend/src/voice/useLiveVoice.ts").read_text(encoding="utf-8")

        self.assertIn("recognition.continuous = true", hook)
        self.assertIn("recognition.interimResults = true", hook)
        self.assertIn("settingsRef.current.silenceMs", hook)
        self.assertIn("submitTranscript", hook)
        self.assertIn("restartListeningSoon", hook)
        self.assertIn("Permissao do microfone negada", hook)

    def test_inworld_tts_consumes_only_assistant_content_in_stable_segments(self):
        hook = (ROOT / "frontend/src/voice/useLiveVoice.ts").read_text(encoding="utf-8")
        text = (ROOT / "frontend/src/voice/voiceText.ts").read_text(encoding="utf-8")
        app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")

        self.assertIn("assistantText: lastAssistantMessage?.content || ''", app)
        self.assertNotIn("assistantMessage?.reasoning", app)
        self.assertIn("extractStreamingSpeechSegments", hook)
        self.assertIn("api.synthesizeInworldSpeech", hook)
        self.assertIn("TTS_PREFETCH_AHEAD = 2", hook)
        self.assertNotIn("SpeechSynthesisUtterance", hook)
        self.assertIn("speechQueueRef", hook)
        self.assertIn("stripFencedCode", text)
        self.assertIn("maxChars", text)
        self.assertIn("prepareStreamingTextForSpeech", text)
        self.assertIn("without changing its length", text)

    def test_live_tts_has_loop_and_cost_guards(self):
        hook = (ROOT / "frontend/src/voice/useLiveVoice.ts").read_text(encoding="utf-8")

        self.assertIn("queuedSegmentKeysRef", hook)
        self.assertIn("MAX_PENDING_TTS_ITEMS = 18", hook)
        self.assertIn("MAX_TTS_SEGMENTS_PER_RESPONSE = 40", hook)
        self.assertIn("MAX_TTS_CHARACTERS_PER_RESPONSE = 6000", hook)
        self.assertIn("!assistantText.startsWith(sourceTextRef.current)", hook)
        self.assertNotIn("consumedUntilRef.current = 0\n    }\n    preparedTextRef.current", hook)

    def test_live_ui_exposes_interrupt_voice_and_privacy_controls(self):
        control = (ROOT / "frontend/src/components/LiveVoiceControl.tsx").read_text(encoding="utf-8")
        message = (ROOT / "frontend/src/components/ChatMessage.tsx").read_text(encoding="utf-8")

        self.assertIn("Interromper", control)
        self.assertIn("Enviar apos silencio", control)
        self.assertIn("Falar respostas automaticamente", control)
        self.assertIn("Minhas vozes clonadas", control)
        self.assertIn("Inworld TTS", control)
        self.assertIn("Desligar modo Live", control)
        self.assertIn("Ouvir resposta", message)
        self.assertIn("Parar voz", message)

    def test_transport_is_cancelled_before_live_resumes(self):
        api = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")
        store = (ROOT / "frontend/src/hooks/useChatStore.ts").read_text(encoding="utf-8")
        websocket = (ROOT / "frontend/src/hooks/useWebSocket.ts").read_text(encoding="utf-8")
        app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")

        self.assertIn("signal?: AbortSignal", api)
        self.assertIn("activeStreamController?.abort()", store)
        self.assertIn("restart", websocket)
        self.assertIn("new WebSocket(WS_BASE, ['chatbot', websocketAuthProtocol(token)])", websocket)
        self.assertNotIn("?token=", websocket)
        self.assertIn("readyState === WebSocket.CONNECTING", websocket)
        self.assertIn("if (wsRef.current !== ws) return", websocket)
        self.assertIn("onInterruptGeneration: handleStop", app)
        self.assertIn("if (wsConnected) restartWs()", app)


if __name__ == "__main__":
    unittest.main()
