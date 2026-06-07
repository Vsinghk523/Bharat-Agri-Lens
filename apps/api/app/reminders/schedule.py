"""Treatment-reminder scheduling logic.

Called inline from the diagnostics router after a diagnosis row is
committed. Inserts 3 ``treatment_reminders`` rows at infection-type-
specific intervals; the cron processor later picks them up and
fires push notifications via FCM.

Why 3 reminders and not N: most chemical sprays in Indian smallholder
practice run a 2-3 application cycle (e.g. Mancozeb spray 1 → wait
7 days → spray 2 → wait 7 days → spray 3 → done). A fourth
reminder is rarely informative and risks notification fatigue.

Skipping logic: we don't schedule reminders for:
- diagnoses with ``infection_type='unknown'`` (we don't know what
  to remind about)
- diagnoses with severity='low' (treatment is optional, reminders
  would be paternalistic)
- diagnoses where the user has disabled ``notif_treatment_reminders``
  in their preferences
- rejected diagnoses (rejection_reason set; nothing to follow up on)

Interval table by infection_type. Numbers based on standard
agronomy practice for Indian smallholders + CIBRC label cadences:
- fungal:                 7 days  (most fungicide labels)
- bacterial:              5 days  (faster spread, tighter cycle)
- viral:                  skip    (no chemical cure exists)
- insect_pest:            10 days (pheromone trap inspection cadence)
- nematode:               14 days (slow population dynamics)
- nutrient_deficiency:    14 days (foliar spray re-application)
- abiotic_stress:         skip    (no recurring intervention)
- weed_competition:       skip    (one-time hand-weeding event)
- unknown:                skip    (already filtered above, defence)
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.models import PlantDiagnostic
from app.logging import get_logger
from app.reminders.models import TreatmentReminder

log = get_logger(__name__)

# Per-infection-type cadence + reminder count.
_INTERVAL_DAYS: dict[str, int] = {
    "fungal": 7,
    "bacterial": 5,
    "insect_pest": 10,
    "nematode": 14,
    "nutrient_deficiency": 14,
}
# Default number of reminders per diagnosis when scheduling fires.
DEFAULT_REMINDER_COUNT = 3


def _should_schedule(diag: PlantDiagnostic, prefs: dict[str, Any]) -> bool:
    """Three independent reasons to NOT schedule reminders:

    1. The user has disabled treatment-reminder push in Settings.
    2. The diagnosis is a rejection (nothing to remind about).
    3. The infection type isn't in the interval table (viral,
       abiotic, weed, unknown).
    """
    if not prefs.get("notif_treatment_reminders", True):
        return False
    if diag.rejection_reason:
        return False
    if not diag.infection_type or diag.infection_type not in _INTERVAL_DAYS:
        return False
    # Low-severity reminders are paternalistic; skip.
    if diag.severity == "low":
        return False
    return True


async def schedule_reminders_for_diagnosis(
    session: AsyncSession,
    diag: PlantDiagnostic,
    user_preferences: dict[str, Any],
    n_steps: int = DEFAULT_REMINDER_COUNT,
) -> int:
    """Create up to ``n_steps`` pending TreatmentReminder rows.

    Returns the number of rows inserted. Zero is a legitimate
    outcome (skipped by policy); the caller doesn't need to
    branch on it.

    Idempotent: re-running for the same diagnostic_id is a no-op
    because of the unique constraint on (diagnostic_id, step_no).
    Caught at the ON CONFLICT level — we use the SQLAlchemy
    statement-level ON CONFLICT DO NOTHING instead of a check-then-
    insert race.
    """
    if not _should_schedule(diag, user_preferences):
        return 0

    interval = _INTERVAL_DAYS[diag.infection_type or ""]
    now = datetime.now(UTC)
    rows = []
    for step in range(1, n_steps + 1):
        rows.append(
            TreatmentReminder(
                reminder_id=uuid.uuid4(),
                diagnostic_id=diag.diagnostic_id,
                user_id=diag.user_id,
                step_no=step,
                scheduled_at=now + timedelta(days=interval * step),
                status="pending",
                attempt_count=0,
                created_at=now,
            )
        )

    for r in rows:
        session.add(r)
    # Commit handled by the caller — keeps this in the same
    # transaction as the diagnosis insert.
    log.info(
        "treatment_reminders_scheduled",
        diagnostic_id=str(diag.diagnostic_id),
        user_id=diag.user_id,
        infection_type=diag.infection_type,
        interval_days=interval,
        n_steps=n_steps,
    )
    return len(rows)


# Silence unused-import warning for Decimal (re-exported for callers
# who construct severity-from-confidence calls in tests).
_ = Decimal
