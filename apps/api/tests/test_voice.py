"""STT + TTS endpoint tests (mock mode)."""

from __future__ import annotations

import base64

from httpx import AsyncClient


async def test_stt_endpoint_mock_mode(
    client: AsyncClient, authed_user: tuple[str, dict[str, str]]
) -> None:
    """Without Bhashini creds, /voice/stt returns a deterministic
    mock transcript describing the audio it received."""
    _, headers = authed_user
    audio = b"\x00\x01\x02\x03\x04\x05"
    r = await client.post(
        "/voice/stt",
        headers=headers,
        json={
            "audio_b64": base64.b64encode(audio).decode(),
            "language": "hi-IN",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "mock"
    assert body["language"] == "hi-IN"
    # Mock format encodes the lang + byte count so we can sanity-check
    # that the audio actually round-tripped through base64.
    assert "hi" in body["transcript"]
    assert "6 bytes" in body["transcript"]


async def test_stt_endpoint_rejects_garbage_base64(
    client: AsyncClient, authed_user: tuple[str, dict[str, str]]
) -> None:
    """Bad base64 → 409, not a 500 with a stack trace."""
    _, headers = authed_user
    r = await client.post(
        "/voice/stt",
        headers=headers,
        json={"audio_b64": "this is !!! not @@ base64", "language": "en-IN"},
    )
    assert r.status_code == 409
    assert "not valid base64" in r.json()["detail"]


async def test_stt_endpoint_requires_token(client: AsyncClient) -> None:
    r = await client.post(
        "/voice/stt",
        json={"audio_b64": base64.b64encode(b"x").decode(), "language": "en-IN"},
    )
    assert r.status_code == 401


async def test_tts_endpoint_mock_mode_returns_playable_wav(
    client: AsyncClient, authed_user: tuple[str, dict[str, str]]
) -> None:
    """The mock path emits an actual WAV that a browser <audio> can play,
    not just any random bytes — verify the RIFF/WAVE header."""
    _, headers = authed_user
    r = await client.post(
        "/voice/tts",
        headers=headers,
        json={"text": "Hello farmer", "language": "hi-IN"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "mock"
    assert body["language"] == "hi-IN"
    assert body["mime_type"] == "audio/wav"

    audio = base64.b64decode(body["audio_b64"])
    # RIFF header sanity: "RIFF<4 size bytes>WAVEfmt "
    assert audio[:4] == b"RIFF"
    assert audio[8:12] == b"WAVE"
    assert audio[12:16] == b"fmt "
    # 8 kHz mono 8-bit silence = 44 byte header + ~3200 byte payload.
    assert 3200 <= len(audio) <= 3300


async def test_tts_endpoint_rejects_empty_text(
    client: AsyncClient, authed_user: tuple[str, dict[str, str]]
) -> None:
    """Pydantic min_length=1 should reject empty input."""
    _, headers = authed_user
    r = await client.post(
        "/voice/tts",
        headers=headers,
        json={"text": "", "language": "en-IN"},
    )
    assert r.status_code == 422


async def test_tts_endpoint_requires_token(client: AsyncClient) -> None:
    r = await client.post(
        "/voice/tts",
        json={"text": "Hello", "language": "en-IN"},
    )
    assert r.status_code == 401


async def test_stt_passthrough_when_input_is_wav(
    client: AsyncClient, authed_user: tuple[str, dict[str, str]]
) -> None:
    """Input that already looks like RIFF/WAVE is forwarded as-is."""
    _, headers = authed_user
    # Smallest plausible WAV header — first 12 bytes are what looks_like_wav checks.
    wav = b"RIFF" + b"\x24\x08\x00\x00" + b"WAVEfmt " + b"\x00" * 8
    r = await client.post(
        "/voice/stt",
        headers=headers,
        json={
            "audio_b64": base64.b64encode(wav).decode(),
            "language": "en-IN",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["audio_conversion"] == "passthrough_wav"


async def test_stt_falls_back_when_ffmpeg_missing(
    client: AsyncClient,
    authed_user: tuple[str, dict[str, str]],
    monkeypatch,
) -> None:
    """Non-WAV input on a host without ffmpeg is forwarded unchanged
    with audio_conversion='passthrough_no_ffmpeg'. The endpoint never
    raises just because the host lacks the binary."""
    monkeypatch.setattr("app.voice.audio.ffmpeg_available", lambda: False)

    _, headers = authed_user
    # WebM EBML magic — definitely not RIFF/WAVE.
    webm_like = b"\x1A\x45\xDF\xA3" + b"\x00" * 20
    r = await client.post(
        "/voice/stt",
        headers=headers,
        json={
            "audio_b64": base64.b64encode(webm_like).decode(),
            "language": "hi-IN",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["audio_conversion"] == "passthrough_no_ffmpeg"
    # Mock transcriber still ran on the raw bytes — 24 = 4 EBML magic + 20 padding.
    assert "24 bytes" in body["transcript"]


async def test_stt_passthrough_on_ffmpeg_failure(
    client: AsyncClient,
    authed_user: tuple[str, dict[str, str]],
    monkeypatch,
) -> None:
    """If ffmpeg is present but rejects the input, we still forward the
    bytes rather than 500."""
    import subprocess

    monkeypatch.setattr("app.voice.audio.ffmpeg_available", lambda: True)

    def boom(_audio: bytes) -> bytes:
        raise subprocess.CalledProcessError(
            returncode=1, cmd=["ffmpeg"], output=b"", stderr=b"bad input"
        )

    monkeypatch.setattr("app.voice.audio._convert_sync", boom)

    _, headers = authed_user
    bogus = b"\xDE\xAD\xBE\xEF" * 4
    r = await client.post(
        "/voice/stt",
        headers=headers,
        json={
            "audio_b64": base64.b64encode(bogus).decode(),
            "language": "en-IN",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["audio_conversion"] == "passthrough_failed"
