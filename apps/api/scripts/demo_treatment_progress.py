r"""Make the 'Step N of 3' treatment-progress indicator visible on the
ActiveHero card on Home.

If you scanned a plant BEFORE the treatment-reminder rails went live
(Trigger #2, migration 0011), your old diagnoses won't have any
treatment_reminders rows attached -- so the progress block stays
hidden even on a high-severity bacterial diagnosis where it should
fire. This script back-fills 3 reminders for the user's most recent
active diagnosis (or one you pass via --diag), then marks the first
one as 'sent' so the UI renders "Step 2 of 3 - Next spray in N days".

Usage
-----
    cd apps/api
    $env:DATABASE_URL = "postgresql+asyncpg://...turntable.proxy.rlwy.net:35980/railway"

    # Default: target Vivek's user, seed 3 reminders on most recent
    # active diagnosis, mark step 1 as sent so the UI shows
    # "Step 2 of 3 - Next spray in N days":
    .\.venv\Scripts\python.exe scripts\demo_treatment_progress.py

    # Show "Step 1 of 3" (no steps sent yet):
    .\.venv\Scripts\python.exe scripts\demo_treatment_progress.py --completed 0

    # Show "Treatment complete":
    .\.venv\Scripts\python.exe scripts\demo_treatment_progress.py --completed 3

    # Remove the demo rows:
    .\.venv\Scripts\python.exe scripts\demo_treatment_progress.py --clean

Safety
------
- Only inserts rows for ONE diagnostic at a time (the chosen one)
- ``--clean`` deletes ONLY the rows it inserted (matched by
  diagnostic_id + step_no)
- Never touches reminders the production scheduler created --
  uses a per-row "demo" marker check via ``attempt_count = -1``
  to distinguish demo rows from real ones
"""
from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.diagnostics.models import PlantDiagnostic

TARGET_USER_ID = "1E2597891F"
# Marker to distinguish demo rows from real ones. The production
# scheduler sets attempt_count = 0 on insert. We use -1 so --clean
# can target ours without risking real reminders.
DEMO_MARKER_ATTEMPT_COUNT = -1
# Interval matching the production schedule.py table.
_INTERVAL_DAYS: dict[str, int] = {
    "fungal": 7,
    "bacterial": 5,
    "insect_pest": 10,
    "nematode": 14,
    "nutrient_deficiency": 14,
}


async def pick_diagnostic(session, diag_id: str | None) -> PlantDiagnostic:
    """Return the diagnostic to demo on. Caller-provided id wins;
    otherwise the most recent non-deleted active diagnosis for the
    target user."""
    if diag_id:
        diag = await session.get(PlantDiagnostic, uuid.UUID(diag_id))
        if not diag:
            raise RuntimeError(f"Diagnostic {diag_id} not found")
        if diag.user_id != TARGET_USER_ID:
            raise RuntimeError(
                f"Diagnostic {diag_id} belongs to {diag.user_id}, "
                f"not {TARGET_USER_ID}. Edit TARGET_USER_ID or pass "
                f"--diag with one owned by the target user."
            )
        return diag

    # Mirror the same filter Home.tsx uses to pick the active-hero
    # diagnosis: must have a real infection_type (not 'unknown'), be
    # in the supported interval table (so the cron would actually
    # have scheduled reminders), and have medium/high/critical
    # severity. Otherwise we'd seed reminders on a Money Plant /
    # unknown row that Home's UI wouldn't even surface.
    result = await session.execute(
        select(PlantDiagnostic)
        .where(
            PlantDiagnostic.user_id == TARGET_USER_ID,
            PlantDiagnostic.deleted_at.is_(None),
            PlantDiagnostic.rejection_reason.is_(None),
            PlantDiagnostic.infection_type.in_(list(_INTERVAL_DAYS.keys())),
            PlantDiagnostic.severity.in_(("medium", "high", "critical")),
        )
        .order_by(desc(PlantDiagnostic.add_date))
        .limit(1)
    )
    diag = result.scalar_one_or_none()
    if not diag:
        raise RuntimeError(
            f"No active-hero-eligible diagnoses found for user "
            f"{TARGET_USER_ID} (need infection_type in "
            f"{sorted(_INTERVAL_DAYS.keys())} and severity in "
            "medium/high/critical). Scan a non-unknown plant first."
        )
    return diag


async def insert_demo_reminders(session, diag: PlantDiagnostic, completed: int) -> None:
    """Insert 3 demo reminder rows for ``diag``, with the first
    ``completed`` of them already marked as 'sent'.

    Uses attempt_count=-1 as a demo marker so --clean can target
    these rows specifically (production reminders use 0+)."""
    interval = _INTERVAL_DAYS.get(diag.infection_type or "", 7)
    now = datetime.now(UTC)
    total = 3

    # Wipe any prior demo rows for this diagnostic so re-runs are
    # idempotent. Doesn't touch real reminders (attempt_count >= 0).
    await session.execute(
        text(
            """
            DELETE FROM treatment_reminders
            WHERE diagnostic_id = :did
              AND attempt_count = :marker
            """
        ),
        {"did": diag.diagnostic_id, "marker": DEMO_MARKER_ATTEMPT_COUNT},
    )

    for step in range(1, total + 1):
        is_sent = step <= completed
        # Scheduled times: spray 1 was N days ago (now sent),
        # spray 2 is +N days from spray 1, etc. So next-pending is
        # always 'interval' days ahead of the most recently sent.
        # When completed=0: spray 1 is +interval days out (future).
        scheduled_at = now + timedelta(days=interval * (step - completed))
        if is_sent:
            # Sent rows: scheduled_at in the past, sent_at = scheduled_at.
            scheduled_at = now - timedelta(days=interval * (completed - step + 1))

        await session.execute(
            text(
                """
                INSERT INTO treatment_reminders
                    (reminder_id, diagnostic_id, user_id, step_no,
                     scheduled_at, status, attempt_count,
                     sent_at, created_at)
                VALUES
                    (:rid, :did, :uid, :step,
                     :scheduled_at, :status, :marker,
                     :sent_at, :created_at)
                """
            ),
            {
                "rid": uuid.uuid4(),
                "did": diag.diagnostic_id,
                "uid": diag.user_id,
                "step": step,
                "scheduled_at": scheduled_at,
                "status": "sent" if is_sent else "pending",
                "marker": DEMO_MARKER_ATTEMPT_COUNT,
                "sent_at": scheduled_at if is_sent else None,
                "created_at": now,
            },
        )

    await session.commit()
    print(
        f"  diagnostic   = {diag.diagnostic_id}\n"
        f"  plant        = {diag.plant_classification}\n"
        f"  infection    = {diag.infection_type} ({interval}-day interval)\n"
        f"  total steps  = {total}\n"
        f"  completed    = {completed} (marked 'sent')\n"
        f"  pending      = {total - completed} (with scheduled_at in future)"
    )


async def delete_demo_reminders(session) -> int:
    """Remove ONLY demo rows (attempt_count = -1) for the target user.
    Production reminders are untouched."""
    result = await session.execute(
        text(
            """
            DELETE FROM treatment_reminders
            WHERE user_id = :uid
              AND attempt_count = :marker
            """
        ),
        {"uid": TARGET_USER_ID, "marker": DEMO_MARKER_ATTEMPT_COUNT},
    )
    await session.commit()
    return result.rowcount or 0


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--completed",
        type=int,
        default=1,
        choices=[0, 1, 2, 3],
        help=(
            "How many of the 3 steps to mark as 'sent'. "
            "0 -> 'Step 1 of 3', 1 -> 'Step 2 of 3' (default), "
            "2 -> 'Step 3 of 3', 3 -> 'Treatment complete'."
        ),
    )
    parser.add_argument(
        "--diag",
        type=str,
        default=None,
        help=(
            "Optional diagnostic_id (UUID) to demo on. Defaults to "
            "the user's most recent non-rejected diagnosis."
        ),
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove demo reminder rows for the target user. Idempotent.",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        if args.clean:
            print(f"Removing demo treatment_reminders rows for {TARGET_USER_ID}...")
            async with Session() as s:
                deleted = await delete_demo_reminders(s)
            print(f"  deleted {deleted} demo row(s)")
            print("Done. Refresh Home -- the progress block disappears.")
        else:
            print(f"Inserting demo treatment_reminders for {TARGET_USER_ID}...")
            async with Session() as s:
                diag = await pick_diagnostic(s, args.diag)
                await insert_demo_reminders(s, diag, args.completed)
            print(
                "\nDone. Refresh Home -- the active-hero card should now show:\n"
                f"  Step {args.completed + 1 if args.completed < 3 else 3} of 3"
                f"  +  Next spray in N days  (in the white pill below severity)\n"
                f"\nWhen you're done, clean up with:\n"
                "  .\\.venv\\Scripts\\python.exe scripts\\demo_treatment_progress.py --clean"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
