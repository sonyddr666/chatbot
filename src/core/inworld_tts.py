"""Authenticated Inworld TTS client with cloned-voice discovery."""

from __future__ import annotations

import asyncio
import base64
import binascii
from dataclasses import dataclass
import time
from typing import Any

import httpx

from src.config import settings


MAX_TTS_TEXT_CHARS = 500
MAX_AUDIO_BYTES = 8 * 1024 * 1024
_synthesis_slots = asyncio.Semaphore(6)
_voice_cache: dict[tuple[str, bool], tuple[float, list[dict[str, Any]]]] = {}
_voice_cache_lock = asyncio.Lock()


class InworldTtsError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SynthesizedAudio:
    content: bytes
    media_type: str
    processed_characters: int
    model_id: str


def inworld_tts_configured() -> bool:
    return bool(settings.inworld_api_key.strip())


def _authorization_header() -> str:
    value = settings.inworld_api_key.strip()
    if not value:
        raise InworldTtsError("INWORLD_API_KEY nao configurada", status_code=503)
    return value if value.lower().startswith("basic ") else f"Basic {value}"


def _headers() -> dict[str, str]:
    return {
        "Authorization": _authorization_header(),
        "Accept": "application/json",
    }


def _base_url() -> str:
    return settings.inworld_tts_base_url.rstrip("/")


def _upstream_error(response: httpx.Response) -> InworldTtsError:
    try:
        payload = response.json()
        detail = payload.get("message") or payload.get("error") or payload.get("detail")
    except (ValueError, TypeError):
        detail = response.text[:300]
    return InworldTtsError(
        f"Inworld retornou HTTP {response.status_code}: {detail or 'erro sem detalhes'}",
        status_code=502,
    )


def _normalized_voice(item: dict[str, Any]) -> dict[str, Any] | None:
    voice_id = str(item.get("voiceId") or "").strip()
    if not voice_id:
        return None
    source = str(item.get("source") or "UNKNOWN").strip().upper()
    return {
        "voice_id": voice_id,
        "display_name": str(item.get("displayName") or voice_id).strip(),
        "language": str(item.get("langCode") or "").strip(),
        "description": str(item.get("description") or "").strip(),
        "source": source,
        "is_cloned": source == "IVC",
        "is_custom": source != "SYSTEM",
        "tags": [str(tag) for tag in (item.get("tags") or []) if str(tag).strip()],
    }


async def _fetch_voice_pages(client: httpx.AsyncClient, filter_expression: str) -> list[dict[str, Any]]:
    voices: list[dict[str, Any]] = []
    page_token = ""
    for _ in range(10):
        params: dict[str, str | int] = {
            "filter": filter_expression,
            "orderBy": "display_name asc",
            "pageSize": 200,
        }
        if page_token:
            params["pageToken"] = page_token
        response = await client.get(
            f"{_base_url()}/voices/v1/voices",
            headers=_headers(),
            params=params,
        )
        if response.status_code >= 400:
            raise _upstream_error(response)
        payload = response.json()
        voices.extend(item for item in payload.get("voices", []) if isinstance(item, dict))
        page_token = str(payload.get("nextPageToken") or "").strip()
        if not page_token:
            break
    return voices


async def list_inworld_voices(language: str = "PT_BR", include_system: bool = True) -> list[dict[str, Any]]:
    """Return workspace clones first, followed by optional system voices."""
    if not inworld_tts_configured():
        raise InworldTtsError("INWORLD_API_KEY nao configurada", status_code=503)

    normalized_language = (language or "PT_BR").strip().replace("-", "_").upper()
    filter_language = normalized_language.split("_", 1)[0].lower()
    cache_key = (normalized_language, include_system)
    now = time.monotonic()
    cached = _voice_cache.get(cache_key)
    if cached and cached[0] > now:
        return [dict(item) for item in cached[1]]

    async with _voice_cache_lock:
        cached = _voice_cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return [dict(item) for item in cached[1]]

        timeout = httpx.Timeout(settings.inworld_tts_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                raw_voices = await _fetch_voice_pages(client, 'source = "IVC"')
                if include_system:
                    raw_voices.extend(
                        await _fetch_voice_pages(
                            client,
                            f'source = "SYSTEM" AND lang_code = "{filter_language}"',
                        )
                    )
        except httpx.TimeoutException as exc:
            raise InworldTtsError("Timeout ao listar vozes Inworld", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise InworldTtsError(f"Falha de rede ao listar vozes Inworld: {exc}") from exc

        deduplicated: dict[str, dict[str, Any]] = {}
        for raw_voice in raw_voices:
            voice = _normalized_voice(raw_voice)
            if voice:
                deduplicated[voice["voice_id"]] = voice
        voices = sorted(
            deduplicated.values(),
            key=lambda item: (not item["is_cloned"], not item["is_custom"], item["display_name"].lower()),
        )
        ttl = max(10, settings.inworld_tts_voice_cache_seconds)
        _voice_cache[cache_key] = (time.monotonic() + ttl, voices)
        return [dict(item) for item in voices]


async def synthesize_inworld_audio(
    text: str,
    voice_id: str,
    *,
    language: str = "pt-BR",
    delivery_mode: str = "BALANCED",
) -> SynthesizedAudio:
    clean_text = (text or "").strip()
    clean_voice_id = (voice_id or "").strip()
    if not clean_text:
        raise InworldTtsError("Texto do TTS nao pode ser vazio", status_code=400)
    if len(clean_text) > MAX_TTS_TEXT_CHARS:
        raise InworldTtsError(f"Trecho TTS excede {MAX_TTS_TEXT_CHARS} caracteres", status_code=400)
    if not clean_voice_id or len(clean_voice_id) > 500:
        raise InworldTtsError("voice_id invalido", status_code=400)

    mode = delivery_mode.strip().upper()
    if mode not in {"STABLE", "BALANCED", "CREATIVE"}:
        raise InworldTtsError("delivery_mode invalido", status_code=400)

    payload = {
        "text": clean_text,
        "voiceId": clean_voice_id,
        "modelId": settings.inworld_tts_model,
        "audioConfig": {
            "audioEncoding": "MP3",
            "language": language,
        },
        "deliveryMode": mode,
        "timestampType": "TIMESTAMP_TYPE_UNSPECIFIED",
        "applyTextNormalization": "OFF",
    }

    timeout = httpx.Timeout(settings.inworld_tts_timeout_seconds)
    try:
        async with _synthesis_slots:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{_base_url()}/tts/v1/voice",
                    headers={**_headers(), "Content-Type": "application/json"},
                    json=payload,
                )
    except httpx.TimeoutException as exc:
        raise InworldTtsError("Timeout ao sintetizar voz Inworld", status_code=504) from exc
    except httpx.HTTPError as exc:
        raise InworldTtsError(f"Falha de rede no TTS Inworld: {exc}") from exc

    if response.status_code >= 400:
        raise _upstream_error(response)
    try:
        data = response.json()
        audio = base64.b64decode(data.get("audioContent") or "", validate=True)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise InworldTtsError("Resposta Inworld sem audio MP3 valido") from exc
    if not audio:
        raise InworldTtsError("Inworld retornou audio vazio")
    if len(audio) > MAX_AUDIO_BYTES:
        raise InworldTtsError("Audio Inworld excedeu o limite permitido")

    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return SynthesizedAudio(
        content=audio,
        media_type="audio/mpeg",
        processed_characters=int(usage.get("processedCharactersCount") or len(clean_text)),
        model_id=str(usage.get("modelId") or settings.inworld_tts_model),
    )
