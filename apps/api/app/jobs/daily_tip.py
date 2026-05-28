"""Daily-tip push: 7 AM IST advisory to opted-in farmers.

Wiring: this module is invoked via two paths.

1. **Programmatic** — ``run_daily_tip_job(session)`` from the admin
   trigger endpoint (``POST /admin/cron/daily-tip``). The endpoint is
   gated by a shared-secret header so a Railway cron service can hit
   it without holding an admin JWT.
2. **CLI** — ``python -m app.jobs.daily_tip`` so a separate Railway
   cron service can run it inside the api container with the right
   DATABASE_URL + FCM credentials, without needing the HTTP layer.

Tip bank: keyed by month-of-year + a small crop-affinity heuristic.
This is intentionally static for v1 — no LLM, no per-user
personalisation. The goal of the trigger is to validate the
end-to-end push pipeline; once it's reliable we can layer
intelligence on top (e.g. swap the tip bank for an LLM call gated
by user crops + region).

Audience filter (in order):
- ``users.preferences.notif_daily_tip == True``  (default: False;
  the user has to opt in for these — they're noisy by definition)
- ``users.status == 'Active'``
- At least one ``Active`` FCM token

This module avoids importing FastAPI on purpose so the standalone
CLI path can `import app.jobs.daily_tip` without pulling in the
HTTP stack.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.logging import get_logger
from app.push.models import FcmToken
from app.push.service import send_to_user, supports_send
from app.users.models import User
from app.users.schemas import UserPreferences

log = get_logger(__name__)

# Tip bank: list of (title, body) tuples. Pick deterministically by
# day-of-year so two consecutive days don't show the same tip. Real
# personalisation (per-crop, per-region) goes in a follow-up.
_TIPS: list[tuple[str, str]] = [
    (
        "Spray in the cool hours",
        "Pesticides work best when applied at sunrise or after sunset — "
        "midday heat causes evaporation and leaf burn.",
    ),
    (
        "Check leaves under the canopy",
        "Most fungal infections start where airflow is low. Lift a few "
        "leaves and look at the undersides before they spread.",
    ),
    (
        "Rotate spray chemistries",
        "Using the same pesticide every cycle accelerates resistance. "
        "Alternate between two FRAC groups across consecutive sprays.",
    ),
    (
        "Water early, not late",
        "Morning irrigation lets foliage dry before nightfall — wet "
        "leaves overnight invite blight and mildew.",
    ),
    (
        "Mind the wind speed",
        "If you can feel a breeze on your face, the spray will drift. "
        "Postpone until winds drop below 10 km/h.",
    ),
    (
        "Yellow stuck-traps go in the field early",
        "Place yellow sticky traps when seedlings emerge. They catch the "
        "first wave of whitefly and aphids before populations explode.",
    ),
    (
        "Compost beats fresh manure",
        "Fresh dung carries weed seeds and ammonia that burn young roots. "
        "Wait 60 days, or use it only between crops.",
    ),
    (
        "Check soil moisture by hand",
        "Squeeze a fistful of soil. If it forms a ball that breaks "
        "when poked, moisture is right. Too crumbly = irrigate; too wet "
        "= wait a day.",
    ),
    (
        "Healthy borders, healthy crop",
        "A 1-metre border of marigold or coriander around your plot pulls "
        "pollinators in and pushes some pests out.",
    ),
    (
        "Scan before you spray",
        "Take a photo and confirm the diagnosis before mixing chemistry. "
        "The wrong product on the right disease is wasted money.",
    ),
]


def pick_tip_for_today(reference: datetime | None = None) -> tuple[str, str]:
    """Pick the day's tip from the bank by day-of-year.

    Deterministic so we can verify locally without leaking randomness
    into observability. ``reference`` lets tests pin the date.
    """
    now = reference or datetime.now(ZoneInfo("Asia/Kolkata"))
    return _TIPS[now.timetuple().tm_yday % len(_TIPS)]


async def run_daily_tip_job(session: AsyncSession) -> dict[str, int]:
    """Fan out today's tip to every opted-in user with an Active FCM token.

    Returns counters for observability:
    - ``eligible``: users that pass the preference + status filter
    - ``sent``:    successful FCM deliveries (sum across devices)

    No exception is raised on partial failure — push is best-effort by
    nature. Per-user failures land in the structured log.
    """
    if not supports_send():
        log.warning("daily_tip_skipped_fcm_off")
        return {"eligible": 0, "sent": 0}

    title, body = pick_tip_for_today()

    # Pull every user who's (a) Active, (b) opted in to daily tips,
    # (c) has at least one Active FCM token. JSONB containment makes
    # the preference filter index-friendly even before we add a
    # functional index.
    rows = (
        await session.execute(
            select(User)
            .join(FcmToken, FcmToken.user_id == User.user_id)
            .where(
                User.status == "Active",
                FcmToken.status == "Active",
                User.preferences["notif_daily_tip"].astext == "true",
            )
            .distinct()
        )
    ).scalars().all()

    eligible = len(rows)
    sent_total = 0
    for user in rows:
        # Defensive double-check on the preference. The SQL filter
        # uses the raw JSONB value; UserPreferences.from_raw applies
        # the canonical default if the key is missing.
        prefs = UserPreferences.from_raw(user.preferences)
        if not prefs.notif_daily_tip:
            continue
        n = await send_to_user(
            session,
            user.user_id,
            title=title,
            body=body,
            data={"type": "daily_tip"},
        )
        sent_total += n

    log.info(
        "daily_tip_job_done",
        eligible=eligible,
        sent=sent_total,
        title=title,
    )
    return {"eligible": eligible, "sent": sent_total}


async def _cli_entry() -> None:
    """CLI entry point: open a session, run the job, exit.

    Used by Railway cron — set the service start command to
    ``python -m app.jobs.daily_tip``. The cron service runs once and
    exits 0; Railway reports success/failure to the cron dashboard.
    """
    # Import here to keep the module HTTP-free.
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        result = await run_daily_tip_job(session)
        # stdout for cron logs / Railway dashboard
        print(f"daily_tip eligible={result['eligible']} sent={result['sent']}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_cli_entry())
