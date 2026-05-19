"""Translation provider abstraction.

We support three text-translation backends:

- **Google Cloud Translate** — fastest path to production. 500 K free
  characters / month, then ~$20 per million. All 22 Indian languages
  plus another 100+. Single API-key auth (no service account dance).
- **Bhashini (ULCA)** — Government of India's free translation gateway.
  Strong support for Indian languages, also exposes STT / TTS we use
  elsewhere. Rate-limited free tier; signup process is gated.
- **Mock** — passthrough that returns the source text unchanged. Used
  in dev / CI when neither provider is configured. Static UI labels
  still localize via the i18next bundles, so the user sees translated
  chrome and English dynamic content — a clear signal to the operator
  that a real provider needs wiring up.

Voice (STT / TTS) is still served by ``BhashiniClient`` directly in
``voice.router``. Only text translation routes through this module.
"""

from __future__ import annotations

import abc
import asyncio
from typing import Any

import httpx

from app.config import get_settings
from app.logging import get_logger
from app.services.bhashini import get_bhashini_client

log = get_logger(__name__)


class Translator(abc.ABC):
    """Common interface for text-translation backends."""

    provider: str = "unknown"

    @property
    def mock_mode(self) -> bool:
        """True when this translator returns inputs unchanged."""
        return False

    @abc.abstractmethod
    async def translate(self, text: str, source: str, target: str) -> str:
        """Translate ``text`` from ``source`` to ``target`` (ISO 639-1).

        Implementations MUST return the original ``text`` on failure
        rather than raise — translation is best-effort enrichment, not
        a hard requirement for the response.
        """

    async def translate_many(
        self,
        texts: list[str | None],
        source: str,
        target: str,
    ) -> list[str | None]:
        """Translate a list of strings. ``None`` values pass through.

        Default implementation translates serially with ``asyncio.gather``.
        Providers that support native batch endpoints (e.g. Google) can
        override for fewer round-trips.
        """
        if source == target:
            return list(texts)

        async def _one(t: str | None) -> str | None:
            if t is None:
                return None
            return await self.translate(t, source, target)

        return await asyncio.gather(*(_one(t) for t in texts))


class MockTranslator(Translator):
    """Passthrough translator for dev / CI."""

    provider = "mock"

    @property
    def mock_mode(self) -> bool:
        return True

    async def translate(self, text: str, source: str, target: str) -> str:
        return text

    async def translate_many(
        self,
        texts: list[str | None],
        source: str,
        target: str,
    ) -> list[str | None]:
        return list(texts)


class BhashiniTranslator(Translator):
    """Adapter that routes translate calls to the existing BhashiniClient."""

    provider = "bhashini"

    def __init__(self) -> None:
        self._client = get_bhashini_client()

    @property
    def mock_mode(self) -> bool:
        return self._client.mock_mode

    async def translate(self, text: str, source: str, target: str) -> str:
        return await self._client.translate(text, source, target)

    async def translate_many(
        self,
        texts: list[str | None],
        source: str,
        target: str,
    ) -> list[str | None]:
        return await self._client.translate_many(texts, source, target)


class GoogleTranslator(Translator):
    """Translate via Google Cloud Translation v2 (simple API-key auth).

    The v2 endpoint accepts an array of ``q`` parameters in one request,
    so we override ``translate_many`` for a single-round-trip batch.
    """

    provider = "google"
    _endpoint = "https://translation.googleapis.com/language/translate/v2"

    def __init__(self, api_key: str, timeout: float = 15.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def translate(self, text: str, source: str, target: str) -> str:
        if not text or source == target:
            return text
        try:
            results = await self._call([text], source, target)
            return results[0] if results else text
        except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
            log.warning(
                "google_translate_failed",
                source=source,
                target=target,
                error=str(exc),
            )
            return text

    async def translate_many(
        self,
        texts: list[str | None],
        source: str,
        target: str,
    ) -> list[str | None]:
        if source == target:
            return list(texts)
        # Filter out None and empty strings; remember their positions so
        # we can splice the translations back in.
        positions: list[int] = []
        payload: list[str] = []
        for i, t in enumerate(texts):
            if t:
                positions.append(i)
                payload.append(t)
        if not payload:
            return list(texts)
        try:
            translated = await self._call(payload, source, target)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning(
                "google_translate_batch_failed",
                source=source,
                target=target,
                error=str(exc),
            )
            return list(texts)
        out: list[str | None] = list(texts)
        for pos, val in zip(positions, translated):
            out[pos] = val
        return out

    async def _call(self, texts: list[str], source: str, target: str) -> list[str]:
        """Single POST to Google Translate v2. Returns the list of
        translatedText values in input order."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                self._endpoint,
                params={"key": self._api_key},
                json={
                    "q": texts,
                    "source": source,
                    "target": target,
                    "format": "text",
                },
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return [t["translatedText"] for t in data["data"]["translations"]]


_singleton: Translator | None = None


def _build_translator() -> Translator:
    s = get_settings()
    pref = (s.translation_provider or "auto").lower()

    has_google = bool(s.google_translate_api_key)
    has_bhashini = bool(s.bhashini_user_id and s.bhashini_api_key)

    if pref == "google":
        if has_google:
            log.info("translator_selected", provider="google")
            return GoogleTranslator(s.google_translate_api_key or "")
        log.warning("translator_google_unconfigured_falling_back_to_mock")
        return MockTranslator()
    if pref == "bhashini":
        log.info(
            "translator_selected",
            provider="bhashini",
            mock=not has_bhashini,
        )
        return BhashiniTranslator()
    if pref == "mock":
        log.info("translator_selected", provider="mock", forced=True)
        return MockTranslator()

    # "auto": prefer Google (fast, stable) > Bhashini > mock.
    if has_google:
        log.info("translator_selected", provider="google", mode="auto")
        return GoogleTranslator(s.google_translate_api_key or "")
    if has_bhashini:
        log.info("translator_selected", provider="bhashini", mode="auto")
        return BhashiniTranslator()
    log.info("translator_selected", provider="mock", mode="auto", reason="no_creds")
    return MockTranslator()


def get_translator() -> Translator:
    """Return the process-wide translator singleton.

    Lazy: built on first access so settings env vars are honoured. Use
    ``reset_translator()`` between tests when env values change.
    """
    global _singleton
    if _singleton is None:
        _singleton = _build_translator()
    return _singleton


def reset_translator() -> None:
    """Drop the cached translator (used by tests when monkeypatching env)."""
    global _singleton
    _singleton = None
