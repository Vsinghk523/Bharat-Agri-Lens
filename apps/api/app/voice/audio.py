"""Audio normalisation for the STT endpoint.

Real Bhashini wants 16 kHz mono WAV. Browser ``MediaRecorder`` defaults
to WebM/Opus on Chrome + Firefox and MP4/AAC on Safari, so we transcode
on the server before forwarding.

Strategy:
1. Sniff the first few bytes — RIFF/WAVE input is passed through
   unchanged (the cheap and common case once mobile clients catch up).
2. Anything else gets piped through ffmpeg with stdin/stdout, no temp
   files. Settings: ``-f wav -acodec pcm_s16le -ac 1 -ar 16000`` matches
   what Bhashini's ASR endpoint expects.
3. If ffmpeg isn't on the PATH (likely in mock-mode dev) we return the
   bytes unchanged and let the caller decide — mock STT doesn't actually
   parse audio, so the dev experience is unaffected.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess

from app.logging import get_logger

log = get_logger(__name__)


def looks_like_wav(audio_bytes: bytes) -> bool:
    """Cheap header check: RIFF/WAVE magic in the first 12 bytes."""
    return len(audio_bytes) >= 12 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE"


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _convert_sync(audio_bytes: bytes) -> bytes:
    """Run ffmpeg with stdin -> stdout. Raises on failure so the caller
    can decide whether to surface or fall back."""
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "wav",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            "16000",
            "pipe:1",
        ],
        input=audio_bytes,
        capture_output=True,
        check=True,
    )
    return proc.stdout


async def to_wav_if_needed(audio_bytes: bytes) -> tuple[bytes, str]:
    """Return ``(possibly-converted bytes, status)``.

    ``status`` is one of:
      - ``passthrough_wav``      — input already RIFF/WAVE
      - ``converted``            — ffmpeg ran successfully
      - ``passthrough_no_ffmpeg`` — ffmpeg not installed; input forwarded
      - ``passthrough_failed``   — ffmpeg failed; input forwarded
    """
    if not audio_bytes:
        return audio_bytes, "passthrough_wav"
    if looks_like_wav(audio_bytes):
        return audio_bytes, "passthrough_wav"
    if not ffmpeg_available():
        log.info("stt_no_ffmpeg", note="forwarding audio as-is")
        return audio_bytes, "passthrough_no_ffmpeg"
    try:
        out = await asyncio.to_thread(_convert_sync, audio_bytes)
        return out, "converted"
    except subprocess.CalledProcessError as exc:
        log.warning(
            "stt_ffmpeg_failed",
            stderr=(exc.stderr or b"").decode("utf-8", "replace")[:300],
        )
        return audio_bytes, "passthrough_failed"
