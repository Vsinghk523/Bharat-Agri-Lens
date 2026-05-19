"""Bhashini integration: translation + ASR (speech-to-text) + TTS.

Bhashini is the Government of India's language gateway: a single API
that fronts open-source translation, speech-to-text, and text-to-speech
models across the major Indian languages. Free tier with daily rate
limits — fine for a couple of thousand farmer queries per day.

Two-call protocol per request:

1. ``POST {pipeline_url}`` (the "getModelsPipeline" endpoint) carrying
   userID + ulcaApiKey headers and a description of what we want to do.
   Bhashini answers with a ``pipelineResponseConfig`` containing a
   ``serviceId`` and a ``pipelineInferenceAPIEndPoint`` block giving
   us a one-shot callback URL plus the auth header to use against it.

2. ``POST {callback_url}`` with the actual input + the chosen
   ``serviceId``. Bhashini answers with the translated / transcribed /
   synthesised output.

In mock mode (both creds empty) we skip the network entirely and
return a deterministic pseudo-translation so the rest of the stack
still exercises the localized response path during local dev and CI.

Language code mapping: our ``preferred_language`` column stores BCP-47
codes (``hi-IN``, ``mr-IN``); Bhashini expects bare ISO 639-1
(``hi``, ``mr``). ``to_bhashini_lang`` strips the region.
"""

from __future__ import annotations

import asyncio
import base64
import struct
from typing import Any

import httpx

from app.config import get_settings
from app.logging import get_logger

log = get_logger(__name__)


def to_bhashini_lang(code: str | None) -> str:
    """Convert a BCP-47 code (``hi-IN``) to a Bhashini code (``hi``).

    Falls back to ``en`` for unknown / empty input so callers can
    safely funnel any string through here.
    """
    if not code:
        return "en"
    return code.split("-")[0].lower()


def _mock_translate(text: str, target: str) -> str:
    """Mock translation: pass the original text through unchanged.

    When the operator hasn't configured BHASHINI_USER_ID + BHASHINI_API_KEY
    we'd rather render readable English than a `target «text»` wrapper
    that confuses end users. The static UI labels still translate (they
    come from i18next bundles, not from this API path), so the result is
    "labels in chosen language, dynamic content in English" — a clear
    signal to operators that Bhashini needs wiring up, without breaking
    the visible product.
    """
    return text


def silence_wav(seconds: float = 0.4, sample_rate: int = 8000) -> bytes:
    """Build a minimal mono 8-bit PCM WAV of N seconds of silence.

    Used by the mock TTS path so the web client gets back a buffer it
    can actually feed to an ``<audio>`` element — silence instead of a
    stack trace when developers try the voice flow before wiring up
    real Bhashini credentials.

    8-bit unsigned PCM uses 0x80 as the centerpoint (silence). Using
    0x00 instead would produce a faint DC offset and a click on play.
    """
    n_samples = int(seconds * sample_rate)
    data = b"\x80" * n_samples
    fmt_chunk_size = 16
    audio_format = 1  # PCM
    num_channels = 1
    bits_per_sample = 8
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    riff_size = 36 + len(data)
    header = (
        b"RIFF"
        + struct.pack("<I", riff_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack(
            "<IHHIIHH",
            fmt_chunk_size,
            audio_format,
            num_channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
        )
        + b"data"
        + struct.pack("<I", len(data))
    )
    return header + data


def _mock_transcribe(audio_bytes: bytes, lang: str) -> str:
    """Deterministic placeholder transcript for the STT mock path."""
    return f"(mock STT • {lang} • {len(audio_bytes)} bytes)"


class BhashiniClient:
    """Thin async wrapper around the Bhashini compute API.

    The client is cheap to construct and intended to live for the
    process lifetime; instantiate once via ``get_bhashini_client()``.
    """

    def __init__(self) -> None:
        s = get_settings()
        self._user_id = s.bhashini_user_id or ""
        self._api_key = s.bhashini_api_key or ""
        self._pipeline_id = s.bhashini_pipeline_id
        self._pipeline_url = s.bhashini_pipeline_url
        self._timeout = s.bhashini_timeout_seconds

    @property
    def mock_mode(self) -> bool:
        """True when no real creds are configured."""
        return not (self._user_id and self._api_key)

    async def translate(self, text: str, source: str, target: str) -> str:
        """Translate ``text`` from ``source`` to ``target`` (ISO 639-1).

        Returns the translated string on success. On any error logs a
        warning and returns the original ``text`` so the caller can
        still render *something* to the user. Returns ``text``
        unchanged when source == target.
        """
        if not text or source == target:
            return text

        if self.mock_mode:
            return _mock_translate(text, target)

        try:
            return await self._translate_via_bhashini(text, source, target)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning(
                "bhashini_translate_failed",
                source=source,
                target=target,
                error=str(exc),
            )
            return text

    async def _translate_via_bhashini(
        self, text: str, source: str, target: str
    ) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            cfg_resp = await client.post(
                self._pipeline_url,
                headers={
                    "userID": self._user_id,
                    "ulcaApiKey": self._api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "pipelineTasks": [
                        {
                            "taskType": "translation",
                            "config": {
                                "language": {
                                    "sourceLanguage": source,
                                    "targetLanguage": target,
                                }
                            },
                        }
                    ],
                    "pipelineRequestConfig": {"pipelineId": self._pipeline_id},
                },
            )
            cfg_resp.raise_for_status()
            cfg = cfg_resp.json()

            inference = cfg["pipelineInferenceAPIEndPoint"]
            callback_url: str = inference["callbackUrl"]
            auth_header: dict[str, Any] = inference["inferenceApiKey"]
            service_id: str = cfg["pipelineResponseConfig"][0]["config"][0]["serviceId"]

            out_resp = await client.post(
                callback_url,
                headers={
                    auth_header["name"]: auth_header["value"],
                    "Content-Type": "application/json",
                },
                json={
                    "pipelineTasks": [
                        {
                            "taskType": "translation",
                            "config": {
                                "language": {
                                    "sourceLanguage": source,
                                    "targetLanguage": target,
                                },
                                "serviceId": service_id,
                            },
                        }
                    ],
                    "inputData": {"input": [{"source": text}]},
                },
            )
            out_resp.raise_for_status()
            payload = out_resp.json()
            return payload["pipelineResponse"][0]["output"][0]["target"]

    async def transcribe(self, audio_bytes: bytes, source: str) -> str:
        """Speech-to-text. ``audio_bytes`` should be WAV/FLAC for real
        Bhashini; mock mode accepts anything and just records the length.

        Returns "" on failure so the caller can decide whether to retry
        or surface an error to the user.
        """
        if not audio_bytes:
            return ""
        if self.mock_mode:
            return _mock_transcribe(audio_bytes, source)
        try:
            return await self._transcribe_via_bhashini(audio_bytes, source)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("bhashini_stt_failed", source=source, error=str(exc))
            return ""

    async def synthesize(
        self,
        text: str,
        source: str,
        gender: str = "female",
    ) -> tuple[bytes, str]:
        """Text-to-speech. Returns ``(audio_bytes, mime_type)``.

        Mock mode returns a short silence WAV (so the browser can still
        play "something"). On Bhashini failure, also returns silence
        plus a logged warning — the caller has already rendered the
        text reply anyway.
        """
        if not text:
            return silence_wav(0.05), "audio/wav"
        if self.mock_mode:
            return silence_wav(), "audio/wav"
        try:
            return await self._synthesize_via_bhashini(text, source, gender)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("bhashini_tts_failed", source=source, error=str(exc))
            return silence_wav(0.05), "audio/wav"

    async def _transcribe_via_bhashini(self, audio_bytes: bytes, source: str) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            cfg = await self._get_pipeline_config(
                client,
                task_type="asr",
                config={"language": {"sourceLanguage": source}},
            )
            service_id = cfg["pipelineResponseConfig"][0]["config"][0]["serviceId"]
            callback_url = cfg["pipelineInferenceAPIEndPoint"]["callbackUrl"]
            auth_header = cfg["pipelineInferenceAPIEndPoint"]["inferenceApiKey"]

            out_resp = await client.post(
                callback_url,
                headers={
                    auth_header["name"]: auth_header["value"],
                    "Content-Type": "application/json",
                },
                json={
                    "pipelineTasks": [
                        {
                            "taskType": "asr",
                            "config": {
                                "language": {"sourceLanguage": source},
                                "serviceId": service_id,
                                "audioFormat": "wav",
                                "samplingRate": 16000,
                            },
                        }
                    ],
                    "inputData": {
                        "audio": [
                            {"audioContent": base64.b64encode(audio_bytes).decode()}
                        ]
                    },
                },
            )
            out_resp.raise_for_status()
            payload = out_resp.json()
            return payload["pipelineResponse"][0]["output"][0]["source"]

    async def _synthesize_via_bhashini(
        self, text: str, source: str, gender: str
    ) -> tuple[bytes, str]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            cfg = await self._get_pipeline_config(
                client,
                task_type="tts",
                config={"language": {"sourceLanguage": source}},
            )
            service_id = cfg["pipelineResponseConfig"][0]["config"][0]["serviceId"]
            callback_url = cfg["pipelineInferenceAPIEndPoint"]["callbackUrl"]
            auth_header = cfg["pipelineInferenceAPIEndPoint"]["inferenceApiKey"]

            out_resp = await client.post(
                callback_url,
                headers={
                    auth_header["name"]: auth_header["value"],
                    "Content-Type": "application/json",
                },
                json={
                    "pipelineTasks": [
                        {
                            "taskType": "tts",
                            "config": {
                                "language": {"sourceLanguage": source},
                                "serviceId": service_id,
                                "gender": gender,
                                "samplingRate": 8000,
                            },
                        }
                    ],
                    "inputData": {"input": [{"source": text}]},
                },
            )
            out_resp.raise_for_status()
            payload = out_resp.json()
            audio_b64 = payload["pipelineResponse"][0]["audio"][0]["audioContent"]
            return base64.b64decode(audio_b64), "audio/wav"

    async def _get_pipeline_config(
        self,
        client: httpx.AsyncClient,
        task_type: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Shared first call: ask Bhashini for a one-shot callback URL."""
        cfg_resp = await client.post(
            self._pipeline_url,
            headers={
                "userID": self._user_id,
                "ulcaApiKey": self._api_key,
                "Content-Type": "application/json",
            },
            json={
                "pipelineTasks": [{"taskType": task_type, "config": config}],
                "pipelineRequestConfig": {"pipelineId": self._pipeline_id},
            },
        )
        cfg_resp.raise_for_status()
        return cfg_resp.json()

    async def translate_many(
        self,
        texts: list[str | None],
        source: str,
        target: str,
    ) -> list[str | None]:
        """Translate a list of strings in parallel. ``None`` passes through."""
        if source == target:
            return list(texts)

        async def _one(t: str | None) -> str | None:
            if t is None:
                return None
            return await self.translate(t, source, target)

        return await asyncio.gather(*(_one(t) for t in texts))


_singleton: BhashiniClient | None = None


def get_bhashini_client() -> BhashiniClient:
    """Process-wide singleton."""
    global _singleton
    if _singleton is None:
        _singleton = BhashiniClient()
    return _singleton


def reset_bhashini_client() -> None:
    """Drop the cached client (used by tests when monkeypatching env)."""
    global _singleton
    _singleton = None
