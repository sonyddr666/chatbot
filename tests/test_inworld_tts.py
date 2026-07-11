import base64
import unittest
from unittest.mock import patch

from src.config import settings
from src.core import inworld_tts


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class FakeAsyncClient:
    responses = []
    requests = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, **kwargs):
        self.requests.append(("GET", url, kwargs))
        return self.responses.pop(0)

    async def post(self, url, **kwargs):
        self.requests.append(("POST", url, kwargs))
        return self.responses.pop(0)


class InworldTtsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.old_key = settings.inworld_api_key
        self.old_model = settings.inworld_tts_model
        settings.inworld_api_key = "workspace-secret"
        settings.inworld_tts_model = "inworld-tts-2"
        inworld_tts._voice_cache.clear()
        FakeAsyncClient.responses = []
        FakeAsyncClient.requests = []

    def tearDown(self):
        settings.inworld_api_key = self.old_key
        settings.inworld_tts_model = self.old_model
        inworld_tts._voice_cache.clear()

    async def test_lists_cloned_voices_before_system_voices(self):
        FakeAsyncClient.responses = [
            FakeResponse(payload={
                "voices": [{
                    "voiceId": "workspace__clone",
                    "displayName": "Minha Voz",
                    "langCode": "PT_BR",
                    "source": "IVC",
                    "tags": ["clone"],
                }]
            }),
            FakeResponse(payload={
                "voices": [{
                    "voiceId": "SystemVoice",
                    "displayName": "Sistema",
                    "langCode": "PT_BR",
                    "source": "SYSTEM",
                }]
            }),
        ]

        with patch("src.core.inworld_tts.httpx.AsyncClient", FakeAsyncClient):
            voices = await inworld_tts.list_inworld_voices("PT_BR", include_system=True)

        self.assertEqual([voice["voice_id"] for voice in voices], ["workspace__clone", "SystemVoice"])
        self.assertTrue(voices[0]["is_cloned"])
        self.assertFalse(voices[1]["is_custom"])
        self.assertEqual(FakeAsyncClient.requests[0][2]["headers"]["Authorization"], "Basic workspace-secret")
        self.assertEqual(
            FakeAsyncClient.requests[1][2]["params"]["filter"],
            'source = "SYSTEM" AND lang_code = "pt"',
        )

    async def test_synthesizes_short_mp3_chunk_without_timestamps(self):
        audio_bytes = b"ID3-inworld-audio"
        FakeAsyncClient.responses = [FakeResponse(payload={
            "audioContent": base64.b64encode(audio_bytes).decode("ascii"),
            "usage": {"processedCharactersCount": 18, "modelId": "inworld-tts-2"},
        })]

        with patch("src.core.inworld_tts.httpx.AsyncClient", FakeAsyncClient):
            result = await inworld_tts.synthesize_inworld_audio(
                "Resposta em trecho.",
                "workspace__clone",
                language="pt-BR",
            )

        self.assertEqual(result.content, audio_bytes)
        self.assertEqual(result.media_type, "audio/mpeg")
        request = FakeAsyncClient.requests[0]
        payload = request[2]["json"]
        self.assertEqual(payload["audioConfig"]["audioEncoding"], "MP3")
        self.assertEqual(payload["applyTextNormalization"], "OFF")
        self.assertEqual(payload["timestampType"], "TIMESTAMP_TYPE_UNSPECIFIED")
        self.assertNotIn("workspace-secret", str(payload))

    async def test_rejects_unconfigured_or_oversized_requests(self):
        settings.inworld_api_key = ""
        with self.assertRaises(inworld_tts.InworldTtsError) as unconfigured:
            await inworld_tts.list_inworld_voices()
        self.assertEqual(unconfigured.exception.status_code, 503)

        settings.inworld_api_key = "workspace-secret"
        with self.assertRaises(inworld_tts.InworldTtsError) as oversized:
            await inworld_tts.synthesize_inworld_audio("x" * 501, "voice")
        self.assertEqual(oversized.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
