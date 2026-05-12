"""Bhashini integration for Indian-language translation (+ STT/TTS later).

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
    """Deterministic placeholder translation for dev / CI.

    Format: ``{target} «{text}»`` — distinctive enough that the
    web app obviously shows "translated" content, while preserving
    the original text so reviewers can sanity-check it.
    """
    return f"{target} «{text}»"


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
