"""Authenticated Inworld TTS routes for low-latency Live playback."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from src.config import settings
from src.core.auth_required import resolve_authorized_user
from src.core.inworld_tts import (
    InworldTtsError,
    inworld_tts_configured,
    list_inworld_voices,
    synthesize_inworld_audio,
)


router = APIRouter(prefix="/tts/inworld", tags=["tts"])


class InworldSynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    voice_id: str = Field(min_length=1, max_length=500)
    language: str = Field(default="pt-BR", min_length=2, max_length=20)
    delivery_mode: str = Field(default="BALANCED", min_length=3, max_length=20)


async def get_current_user(authorization: str | None = Header(default=None)):
    user = resolve_authorized_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Nao autenticado")
    return user


def _tts_http_error(exc: InworldTtsError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/status")
async def inworld_status(user=Depends(get_current_user)):
    return {
        "configured": inworld_tts_configured(),
        "model": settings.inworld_tts_model,
        "default_voice": settings.inworld_tts_default_voice,
        "provider": "inworld",
    }


@router.get("/voices")
async def inworld_voices(
    language: str = Query(default="PT_BR", min_length=2, max_length=20),
    include_system: bool = Query(default=True),
    user=Depends(get_current_user),
):
    try:
        voices = await list_inworld_voices(language, include_system=include_system)
    except InworldTtsError as exc:
        raise _tts_http_error(exc) from exc
    return {
        "configured": True,
        "provider": "inworld",
        "model": settings.inworld_tts_model,
        "default_voice": settings.inworld_tts_default_voice,
        "voices": voices,
        "cloned_count": sum(1 for voice in voices if voice["is_cloned"]),
    }


@router.post("/synthesize")
async def inworld_synthesize(body: InworldSynthesisRequest, user=Depends(get_current_user)):
    try:
        audio = await synthesize_inworld_audio(
            body.text,
            body.voice_id,
            language=body.language,
            delivery_mode=body.delivery_mode,
        )
    except InworldTtsError as exc:
        raise _tts_http_error(exc) from exc
    return Response(
        content=audio.content,
        media_type=audio.media_type,
        headers={
            "Cache-Control": "no-store",
            "X-Inworld-Model": audio.model_id,
            "X-Inworld-Processed-Characters": str(audio.processed_characters),
            "X-Inworld-Cache": "HIT" if audio.cache_hit else "MISS",
        },
    )
