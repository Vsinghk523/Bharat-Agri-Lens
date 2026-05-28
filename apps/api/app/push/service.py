"""FCM push delivery — initialization, send helpers, stale-token reaping.

Initialization: we accept the Firebase service-account credentials in
*one* of three forms (in order of preference):

1. ``FIREBASE_SERVICE_ACCOUNT_BASE64`` — Base64-encoded JSON. Best for
   Railway: a multi-line PEM block doesn't survive env-var entry.
2. ``FIREBASE_SERVICE_ACCOUNT_JSON`` — raw JSON string. Works locally
   if you escape newlines correctly.
3. ``FIREBASE_SERVICE_ACCOUNT_FILE`` — path to a JSON file on disk.
   Convenient for ``apps/api/.env``-style local dev.

If none are set, ``_get_app()`` returns ``None`` and every send call
becomes a no-op + warning log. This keeps the test suite + early-stage
dev runs from crashing when Firebase isn't wired up yet.

Send strategy: best-effort. We fan out to all of a user's
``Active`` FCM tokens, log per-token outcomes, increment
``failure_count`` on permanent FCM errors, and mark a token ``Stale``
after 3 consecutive permanent failures (UNREGISTERED, INVALID_ARGUMENT).
Transient errors don't increment the counter.

This module is intentionally side-effect-light: callers should
fire-and-forget via ``asyncio.create_task`` if the caller is on a
hot path (e.g. a request handler) — we don't want a slow FCM round
trip to block an HTTP response.
"""
from __future__ import annotations

import base64
import json
from typing import Any

import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.logging import get_logger
from app.push.models import FcmToken

log = get_logger(__name__)

# Permanent error codes per Firebase docs — these mean the token is dead.
_DEAD_TOKEN_CODES = {
    "registration-token-not-registered",
    "invalid-registration-token",
    "invalid-argument",
}

_app: firebase_admin.App | None = None
_init_attempted = False


def _load_credentials() -> credentials.Certificate | None:
    """Resolve Firebase service-account credentials from env.

    Returns ``None`` if no source is configured — callers treat this
    as "FCM disabled" and skip the send.
    """
    s = get_settings()
    if s.firebase_service_account_base64:
        try:
            raw = base64.b64decode(s.firebase_service_account_base64)
            data = json.loads(raw)
            return credentials.Certificate(data)
        except (ValueError, json.JSONDecodeError) as exc:
            log.error("fcm_credentials_base64_parse_failed", error=str(exc))
            return None
    if s.firebase_service_account_json:
        try:
            data = json.loads(s.firebase_service_account_json)
            return credentials.Certificate(data)
        except json.JSONDecodeError as exc:
            log.error("fcm_credentials_json_parse_failed", error=str(exc))
            return None
    if s.firebase_service_account_file:
        try:
            return credentials.Certificate(s.firebase_service_account_file)
        except (FileNotFoundError, ValueError) as exc:
            log.error(
                "fcm_credentials_file_load_failed",
                path=s.firebase_service_account_file,
                error=str(exc),
            )
            return None
    return None


def _get_app() -> firebase_admin.App | None:
    """Lazy + idempotent Firebase Admin initialization.

    Memoizes the init attempt so we don't spam logs when FCM isn't
    configured — the first attempt fails and every subsequent call
    short-circuits.
    """
    global _app, _init_attempted
    if _app is not None:
        return _app
    if _init_attempted:
        return None
    _init_attempted = True
    cred = _load_credentials()
    if cred is None:
        log.warning("fcm_not_configured", note="set FIREBASE_SERVICE_ACCOUNT_* to enable push")
        return None
    try:
        _app = firebase_admin.initialize_app(cred)
        log.info("fcm_initialized")
        return _app
    except (ValueError, firebase_admin.exceptions.FirebaseError) as exc:
        log.error("fcm_init_failed", error=str(exc))
        return None


async def get_active_tokens(session: AsyncSession, user_id: str) -> list[FcmToken]:
    """All non-stale FCM tokens for a user."""
    result = await session.execute(
        select(FcmToken).where(
            FcmToken.user_id == user_id,
            FcmToken.status == "Active",
        )
    )
    return list(result.scalars().all())


def _build_message(
    token: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> messaging.Message:
    """Compose a generic FCM message. ``data`` keys/values MUST be strings
    per FCM's payload constraints — we let callers coerce ints to str."""
    return messaging.Message(
        token=token,
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                # Lets us style by category on the Android side later
                # (icon, color, sound). For v1 we just set a channel.
                channel_id="default",
            ),
        ),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default"),
            ),
        ),
    )


async def send_to_user(
    session: AsyncSession,
    user_id: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> int:
    """Fan-out push to all of a user's Active FCM tokens.

    Returns the number of successful deliveries. Failures are logged
    and accounted in the per-token ``failure_count`` so we can reap
    dead tokens. The caller doesn't get to retry — pushes are best-
    effort and noise-tolerant by nature.
    """
    if _get_app() is None:
        return 0
    tokens = await get_active_tokens(session, user_id)
    if not tokens:
        return 0

    succeeded = 0
    for tok in tokens:
        try:
            messaging.send(_build_message(tok.token, title, body, data))
            succeeded += 1
            tok.failure_count = 0
        except messaging.UnregisteredError:
            tok.failure_count += 1
            _maybe_stale(tok)
            log.info("fcm_token_dead", user_id=user_id, reason="UNREGISTERED")
        except (messaging.ApiCallError, ValueError) as exc:
            err_code = getattr(exc, "code", "")
            if err_code in _DEAD_TOKEN_CODES:
                tok.failure_count += 1
                _maybe_stale(tok)
            log.warning(
                "fcm_send_failed",
                user_id=user_id,
                code=err_code,
                error=str(exc),
            )

    await session.commit()
    return succeeded


def _maybe_stale(tok: FcmToken) -> None:
    """Mark a token Stale after 3 consecutive permanent failures.

    Three strikes (rather than one) absorbs transient noise where
    FCM occasionally returns INVALID_ARGUMENT for what is in fact a
    live token (rare, but happens during their rolling deploys).
    """
    if tok.failure_count >= 3:
        tok.status = "Stale"


async def reap_stale_tokens(session: AsyncSession, user_id: str) -> int:
    """Mark all of a user's non-zero-failure tokens as Stale.

    Used by the sign-out path so a dead device doesn't keep getting
    targeted by daily-tip cron pushes the user already implicitly
    declined when they signed out.
    """
    result = await session.execute(
        update(FcmToken)
        .where(FcmToken.user_id == user_id, FcmToken.status == "Active")
        .values(status="Stale")
    )
    await session.commit()
    return result.rowcount or 0


def supports_send() -> bool:
    """Cheap probe for the daily-tip cron + admin trigger: is FCM
    actually usable, or did init fail? Avoids spinning up DB cursors
    to load tokens when we already know the send will no-op."""
    return _get_app() is not None
