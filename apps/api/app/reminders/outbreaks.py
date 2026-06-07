"""Hyperlocal outbreak detection + alert dispatch (Trigger #3).

The big idea: every day, look at the last 7 days of diagnoses
grouped by ``(users.pincode, plant_diagnostics.infection_type)``.
Any group with ``>= OUTBREAK_THRESHOLD`` reports is an outbreak.
Notify everyone else in that pincode — they should watch their
crops closely.

Why pincode and not city/state
------------------------------
- Pincodes in India cover ~5-30 km² each and roughly track
  agroclimatic conditions (rainfall, soil type, growing season).
  A fungal pressure that exists in pincode 411001 is far more
  likely to affect another farmer in 411001 than one in 411046,
  even if both call their city "Pune".
- Pincode is plaintext in the DB (see migration 0011) which lets
  us GROUP BY it cheaply. City + state are encrypted via Fernet,
  which would break SQL aggregation.

Audience filter — defence in depth
----------------------------------
1. ``users.pincode = outbreak.pincode`` (in the affected area)
2. ``user_id NOT IN reporter_ids`` (the reporters already know;
   nudging them is annoying and confusing)
3. ``status = 'Active'`` (skip soft-deleted accounts)
4. ``preferences.notif_outbreak_alerts IS NOT False`` (default-on,
   re-checked at send time so a Settings flip takes effect on
   the next tick)
5. Not already notified about this exact outbreak this week (the
   ``outbreak_alerts`` UNIQUE constraint on
   ``(user_id, pincode, infection_type, week_key)``)

Edge cases handled
------------------
- Users without a pincode set: skipped entirely. Onboarding now
  asks for pincode but legacy users have NULL until they edit
  their Profile.
- Diagnostics with ``infection_type IN (NULL, 'unknown')``: not
  counted. They don't represent a confirmed disease.
- Diagnostics with ``rejection_reason`` set (OOD-rejected): not
  counted. The model refused — there's no real signal.
- Diagnostics older than ``WINDOW_DAYS``: not counted.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.models import PlantDiagnostic
from app.logging import get_logger
from app.push.service import send_to_user, supports_send
from app.reminders.models import OutbreakAlert
from app.users.models import User
from app.users.schemas import UserPreferences

log = get_logger(__name__)

# Tunables. Documented at module level so changing them is easy
# without spelunking through the function body.
OUTBREAK_THRESHOLD = 5  # ≥ this many same-disease reports in the same pincode
WINDOW_DAYS = 7         # rolling window we evaluate over
DEDUP_WEEKS = 1         # how often the same user can be re-notified about the same disease in the same pincode


def _current_week_key() -> str:
    """ISO-8601 week key like ``2026-W23``. Coarse enough that two
    consecutive cron runs over the same outbreak don't double-fire."""
    now = datetime.now(UTC).isocalendar()
    return f"{now.year}-W{now.week:02d}"


def _friendly_disease_label(infection_type: str) -> str:
    """User-facing copy for the push body. The DB stores enum-ish
    values (``fungal``, ``bacterial``, …) but the farmer reads
    "fungal infection", not the raw token."""
    return {
        "fungal": "fungal infection",
        "bacterial": "bacterial infection",
        "viral": "viral infection",
        "insect_pest": "insect / pest damage",
        "nematode": "nematode infestation",
        "nutrient_deficiency": "nutrient deficiency",
        "abiotic_stress": "weather / abiotic stress",
        "weed_competition": "weed pressure",
    }.get(infection_type, infection_type)


async def detect_outbreaks(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Aggregate the last 7 days of diagnostics by ``(pincode, infection_type)``
    and return every group at or above threshold.

    Each returned dict:
        {
          "pincode": "411001",
          "infection_type": "fungal",
          "report_count": 7,
          "reporter_ids": ["U001", "U023", ...],
        }

    Postgres-specific ``array_agg`` is fine — we're already PG-only
    for JSONB, encryption, etc.
    """
    cutoff = datetime.now(UTC) - timedelta(days=WINDOW_DAYS)
    # JOIN diagnostics to users to get the pincode of each report.
    # Filter at the SQL level so we never serialise heavy rows just
    # to discard them in Python.
    stmt = text(
        """
        SELECT u.pincode AS pincode,
               d.infection_type AS infection_type,
               COUNT(*) AS report_count,
               array_agg(DISTINCT d.user_id) AS reporter_ids
          FROM plant_diagnostics d
          JOIN users u ON u.user_id = d.user_id
         WHERE d.deleted_at IS NULL
           AND d.rejection_reason IS NULL
           AND d.infection_type IS NOT NULL
           AND d.infection_type <> 'unknown'
           AND u.pincode IS NOT NULL
           AND d.add_date >= :cutoff
         GROUP BY u.pincode, d.infection_type
        HAVING COUNT(*) >= :threshold
        """
    )
    rows = (
        await session.execute(stmt, {"cutoff": cutoff, "threshold": OUTBREAK_THRESHOLD})
    ).mappings().all()
    return [
        {
            "pincode": r["pincode"],
            "infection_type": r["infection_type"],
            "report_count": int(r["report_count"]),
            "reporter_ids": list(r["reporter_ids"] or []),
        }
        for r in rows
    ]


async def _audience_for_outbreak(
    session: AsyncSession,
    pincode: str,
    reporter_ids: list[str],
    week_key: str,
    infection_type: str,
) -> list[User]:
    """Find users in this pincode who should be notified.

    Filters:
    - Same pincode
    - NOT a reporter (they already know)
    - Active status
    - Not already notified this week about this exact outbreak

    Returns User rows so the caller can re-read prefs from JSONB
    without an extra round trip per user.
    """
    # Build the "already notified this week" subquery first; it's a
    # tiny table so EXISTS is fine.
    already_stmt = (
        select(OutbreakAlert.user_id)
        .where(
            OutbreakAlert.pincode == pincode,
            OutbreakAlert.infection_type == infection_type,
            OutbreakAlert.week_key == week_key,
        )
    )
    already_ids = [row[0] for row in (await session.execute(already_stmt)).all()]

    # Now the audience query.
    audience_stmt = select(User).where(
        User.pincode == pincode,
        User.status == "Active",
        User.deleted_at.is_(None),
    )
    if reporter_ids:
        audience_stmt = audience_stmt.where(User.user_id.notin_(reporter_ids))
    if already_ids:
        audience_stmt = audience_stmt.where(User.user_id.notin_(already_ids))

    return list((await session.execute(audience_stmt)).scalars().all())


async def run_outbreak_cron(session: AsyncSession) -> dict[str, int]:
    """Top-level entry point. Returns counters for observability:

        {
          "outbreaks_detected": 3,
          "users_considered": 28,
          "pushes_sent": 22,
          "skipped_pref": 4,
          "skipped_no_fcm": 2,
        }
    """
    counters: dict[str, int] = {
        "outbreaks_detected": 0,
        "users_considered": 0,
        "pushes_sent": 0,
        "skipped_pref": 0,
        "skipped_no_fcm": 0,
        "alerts_recorded": 0,
    }

    if not supports_send():
        log.warning("outbreak_cron_skipped_fcm_off")
        return counters

    outbreaks = await detect_outbreaks(session)
    counters["outbreaks_detected"] = len(outbreaks)
    if not outbreaks:
        log.info("outbreak_cron_no_outbreaks")
        return counters

    week_key = _current_week_key()
    now = datetime.now(UTC)

    for outbreak in outbreaks:
        audience = await _audience_for_outbreak(
            session,
            outbreak["pincode"],
            outbreak["reporter_ids"],
            week_key,
            outbreak["infection_type"],
        )
        counters["users_considered"] += len(audience)

        disease_label = _friendly_disease_label(outbreak["infection_type"])
        title = "Outbreak alert near you"
        body = (
            f"{outbreak['report_count']} farmers in your pincode "
            f"reported {disease_label} in the last {WINDOW_DAYS} days. "
            f"Watch your crops closely."
        )

        for user in audience:
            # Re-check preferences at send time. A Settings flip after
            # the cron started should take effect immediately.
            prefs = UserPreferences.from_raw(user.preferences)
            if not prefs.notif_outbreak_alerts:
                counters["skipped_pref"] += 1
                continue

            try:
                delivered = await send_to_user(
                    session,
                    user.user_id,
                    title=title,
                    body=body,
                    data={
                        "type": "outbreak_alert",
                        "pincode": outbreak["pincode"],
                        "infection_type": outbreak["infection_type"],
                        "report_count": str(outbreak["report_count"]),
                    },
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "outbreak_send_raised",
                    user_id=user.user_id,
                    error=str(exc),
                )
                delivered = 0

            if delivered > 0:
                counters["pushes_sent"] += 1

            # Record the alert regardless of FCM success — we don't
            # want to spam the user with retries on subsequent ticks.
            # If the push genuinely failed, the worst case is they see
            # the "In your area" panel on Home without having received
            # the push, which is the right "second-chance" UX.
            session.add(
                OutbreakAlert(
                    alert_id=uuid.uuid4(),
                    user_id=user.user_id,
                    pincode=outbreak["pincode"],
                    infection_type=outbreak["infection_type"],
                    week_key=week_key,
                    notified_at=now,
                    report_count=outbreak["report_count"],
                )
            )
            counters["alerts_recorded"] += 1

    await session.commit()
    log.info("outbreak_cron_done", **counters)
    return counters


async def _cli_entry() -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        result = await run_outbreak_cron(session)
        print(json.dumps(result, default=str))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_cli_entry())
