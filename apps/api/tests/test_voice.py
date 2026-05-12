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
