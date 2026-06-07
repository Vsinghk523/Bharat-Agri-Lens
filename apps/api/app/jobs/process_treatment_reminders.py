"""Hourly cron: fire due treatment reminders.

Picks up every ``treatment_reminders`` row where:
  - ``status = 'pending'``
  - ``scheduled_at <= now()``
  - ``dismissed_at IS NULL``

For each row:
  1. Look up the diagnostic + the user's preferences
  2. Skip if the user has since disabled notif_treatment_reminders
     (we don't pre-cancel rows; instead, we re-check at fire time so
     a Settings flip takes effect on the next cron run)
  3. Send the FCM push
  4. Update status → 'sent' (or 'failed' after 3 attempts)

The 3-strikes pattern matches send_to_user's per-token failure
handling: transient errors get retried on the next hourly tick;
permanent errors mark the row failed.

Invocation: ``POST /admin/cron/process-treatment-reminders`` with
the ``X-Cron-Secret`` header, same as the other cron endpoints. Or
``python -m app.jobs.process_treatment_reminders`` for CLI / Railway
cron service runs.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.models import PlantDiagnostic
from app.logging import get_logger
from app.push.service import send_to_user, supports_send
from app.reminders.models import TreatmentReminder
from app.users.models import User
from app.users.schemas import UserPreferences

log = get_logger(__name__)

# Short, action-oriented push copy. Step-specific so the second
# reminder reads differently from the first (avoids "Why is the same
# message coming again?" confusion).
_STEP_COPY: dict[int, tuple[str, str]] = {
    1: (
        "Time for the first spray",
        "{plant} — {disease}. Apply the recommended treatment today; "
        "morning is best.",
    ),
    2: (
        "Second-spray reminder",
        "Follow-up spray due today for {plant} ({disease}). Same dose, "
        "same conditions as before.",
    ),
    3: (
        "Final spray of the cycle",
        "Last scheduled spray for {plant} ({disease}). Inspect leaves "
        "afterwards to confirm the disease is under control.",
    ),
}


def _format_message(diag: PlantDiagnostic, step_no: int) -> tuple[str, str]:
    """Pick step-specific copy and substitute plant + disease."""
    title, body_tpl = _STEP_COPY.get(
        step_no,
        ("Treatment reminder", "Follow up on your {plant} — {disease} diagnosis."),
    )
    plant = diag.plant_classification or "your crop"
    disease = (
        diag.correct_disease
        or diag.disease_name
        or diag.correct_infection_type
        or diag.infection_type
        or "the diagnosis"
    )
    return title, body_tpl.format(plant=plant, disease=disease)


async def run_reminder_cron(session: AsyncSession) -> dict[str, int]:
    """Process every due, pending reminder. Returns counters.

    Safe to run multiple times in an hour — the status flip from
    pending → sent is atomic, and any concurrent worker that pulls
    the same row will just skip it on the second pass.
    """
    counters = {"considered": 0, "sent": 0, "skipped_pref": 0, "failed": 0}
    if not supports_send():
        log.warning("reminder_cron_skipped_fcm_off")
        return counters

    now = datetime.now(UTC)
    # Join diagnostics so we have access to the plant + disease for the
    # message body. Filter at the SQL level to avoid loading large
    # batches into memory only to discard them.
    stmt = (
        select(TreatmentReminder, PlantDiagnostic, User)
        .join(
            PlantDiagnostic,
            PlantDiagnostic.diagnostic_id == TreatmentReminder.diagnostic_id,
        )
        .join(User, User.user_id == TreatmentReminder.user_id)
        .where(
            TreatmentReminder.status == "pending",
            TreatmentReminder.scheduled_at <= now,
            TreatmentReminder.dismissed_at.is_(None),
        )
        # Cap each tick so a long backlog can't OOM the worker — the
        # next tick picks up the rest. 500 covers any plausible scale
        # while staying comfortably within memory.
        .limit(500)
    )
    triples = (await session.execute(stmt)).all()
    counters["considered"] = len(triples)

    for reminder, diag, user in triples:
        # Re-check user prefs at fire time — a Settings flip after the
        # row was scheduled must take effect on the next tick.
        prefs = UserPreferences.from_raw(user.preferences)
        if not prefs.notif_treatment_reminders:
            reminder.status = "dismissed"
            reminder.dismissed_at = now
            counters["skipped_pref"] += 1
            continue

        title, body = _format_message(diag, reminder.step_no)
        try:
            delivered = await send_to_user(
                session,
                reminder.user_id,
                title=title,
                body=body,
                data={
                    "type": "treatment_reminder",
                    "diagnostic_id": str(reminder.diagnostic_id),
                    "step_no": str(reminder.step_no),
                },
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "reminder_send_raised",
                reminder_id=str(reminder.reminder_id),
                error=str(exc),
            )
            delivered = 0

        reminder.attempt_count += 1
        if delivered > 0:
            reminder.status = "sent"
            reminder.sent_at = now
            counters["sent"] += 1
        elif reminder.attempt_count >= 3:
            reminder.status = "failed"
            counters["failed"] += 1
        # Else: stays pending; next tick retries.

    await session.commit()
    log.info("reminder_cron_done", **counters)
    return counters


async def _cli_entry() -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        result = await run_reminder_cron(session)
        print(json.dumps(result, default=str))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_cli_entry())
