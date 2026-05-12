"""Voice I/O — STT (ASR) and TTS via Bhashini.

The web client never talks to Bhashini directly; it ships raw audio
through these endpoints and gets back a transcript / a wav. Auth-gated
because both directions consume Bhashini's rate-limited free quota.

Audio is passed as base64 inside JSON to keep the API style consistent
with the rest of the surface. Browser ``MediaRecorder`` defaults to
WebM/Opus on Chrome + Firefox, so the STT route transcodes to 16 kHz
mono WAV via ffmpeg before forwarding to Bhashini (see ``audio.py``).
Mock mode accepts anything and doesn't care.
"""

from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.common.errors import ConflictError
from app.services.bhashini import get_bhashini_client, to_bhashini_lang
from app.users.models import User
from app.voice.audio import to_wav_if_needed
from app.voice.schemas import SttRequest, SttResponse, TtsRequest, TtsResponse

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/stt", response_model=SttResponse)
async def stt(
    payload: SttRequest,
    _: User = Depends(get_current_user),
) -> SttResponse:
    """Decode audio bytes -> ASR transcript.

    WebM/Opus from MediaRecorder is transcoded to 16 kHz mono WAV via
    ffmpeg before being handed to Bhashini. WAV input is passed through
    untouched.
    """
    try:
        audio_bytes = base64.b64decode(payload.audio_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ConflictError(f"audio_b64 is not valid base64: {exc}") from exc

    wav_bytes, conversion_status = await to_wav_if_needed(audio_bytes)

    client = get_bhashini_client()
    src = to_bhashini_lang(payload.language)
    transcript = await client.transcribe(wav_bytes, src)
    return SttResponse(
        transcript=transcript,
        language=payload.language,
        provider="mock" if client.mock_mode else "bhashini",
        audio_conversion=conversion_status,  # type: ignore[arg-type]
    )


@router.post("/tts", response_model=TtsResponse)
async def tts(
    payload: TtsRequest,
    _: User = Depends(get_current_user),
) -> TtsResponse:
    """Synthesise audio bytes for the given text. Returns base64."""
    client = get_bhashini_client()
    src = to_bhashini_lang(payload.language)
    audio_bytes, mime = await client.synthesize(payload.text, src, payload.gender)
    return TtsResponse(
        audio_b64=base64.b64encode(audio_bytes).decode(),
        mime_type=mime,
        language=payload.language,
        provider="mock" if client.mock_mode else "bhashini",
    )
