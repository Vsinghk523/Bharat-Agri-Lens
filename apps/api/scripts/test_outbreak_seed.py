"""End-to-end test of Trigger #3 — outbreak detection + audience filter.

What it does
------------
1. Cleans any leftover rows from a prior run (idempotent restart).
2. Seeds 5 ``reporter`` test users in pincode 411001, each with one
   fungal/medium diagnosis from today.
3. Seeds 1 ``audience`` test user in the same pincode (no diagnosis).
4. POSTs to the prod ``/admin/cron/process-outbreak-alerts`` endpoint.
5. Prints the cron's counter response and the rows it inserted into
   ``outbreak_alerts``.
6. Cleans everything up — no test artefacts remain in prod.

What you should see
-------------------
A successful run prints something like::

    Seeded 5 reporters + 1 audience in pincode 411001
    Cron response: {
        'outbreaks_detected': 1,        ← 411001 + fungal hit threshold
        'users_considered': 1,          ← only the audience user (reporters are excluded)
        'pushes_sent': 0,               ← 0 because the test user has no FCM token
        'skipped_pref': 0,
        'skipped_no_fcm': 0,
        'alerts_recorded': 1
    }
      Alert recorded: {'user_id': 'OUTBKAUDI0', 'pincode': '411001',
                       'infection_type': 'fungal', 'report_count': 5}
    Cleanup done.

If you want to ALSO see the panel on the Home page UI:
- Temporarily set YOUR account's pincode to 411001 (Profile → PIN code)
- Re-run this script (or comment out the cleanup line)
- Refresh Home in the browser — the saffron "In your area" panel
  appears at the top

Run
---
    cd apps/api
    # set DATABASE_URL to prod (via railway-run or manually):
    .\.venv\Scripts\python.exe scripts\test_outbreak_seed.py
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings

CRON_URL = (
    "https://api-production-d64e.up.railway.app/admin/cron/process-outbreak-alerts"
)
CRON_SECRET = "lnzw8ch5ykp39jvufser046a1iqg7mdtob2x"

TEST_PINCODE = "411001"
TEST_INFECTION = "fungal"

REPORTER_IDS = [f"OUTBKREP{i:02d}" for i in range(5)]
AUDIENCE_IDS = ["OUTBKAUDI0"]
ALL_TEST_IDS = REPORTER_IDS + AUDIENCE_IDS


async def cleanup(session: Any) -> None:
    """Idempotent delete of every test artefact this script could leave."""
    ids = ALL_TEST_IDS
    # Order matters because of FK constraints, even though most cascade:
    await session.execute(
        text("DELETE FROM outbreak_alerts WHERE user_id = ANY(:ids)"),
        {"ids": ids},
    )
    await session.execute(
        text(
            "DELETE FROM diagnostic_followup_questions "
            "WHERE diagnostic_id IN (SELECT diagnostic_id FROM plant_diagnostics "
            "WHERE user_id = ANY(:ids))"
        ),
        {"ids": ids},
    )
    await session.execute(
        text("DELETE FROM treatment_reminders WHERE user_id = ANY(:ids)"),
        {"ids": ids},
    )
    await session.execute(
        text("DELETE FROM plant_diagnostics WHERE user_id = ANY(:ids)"),
        {"ids": ids},
    )
    await session.execute(
        text("DELETE FROM fcm_tokens WHERE user_id = ANY(:ids)"),
        {"ids": ids},
    )
    await session.execute(
        text("DELETE FROM users WHERE user_id = ANY(:ids)"),
        {"ids": ids},
    )
    await session.commit()


async def seed(session: Any) -> None:
    """Insert reporters + audience + reporter diagnostics."""
    for i, uid in enumerate(REPORTER_IDS):
        await session.execute(
            text(
                """
                INSERT INTO users
                    (user_id, user_email, isd_code, mobile_no, country, pincode, role,
                     status, add_date, modify_date)
                VALUES
                    (:uid, :email, '91', :mobile, 'IN', :pin, 'user',
                     'Active', now(), now())
                """
            ),
            {
                "uid": uid,
                "email": f"test-{uid.lower()}@example.com",
                "mobile": 919900000000 + i,
                "pin": TEST_PINCODE,
            },
        )
    for i, uid in enumerate(AUDIENCE_IDS):
        await session.execute(
            text(
                """
                INSERT INTO users
                    (user_id, user_email, isd_code, mobile_no, country, pincode, role,
                     status, add_date, modify_date)
                VALUES
                    (:uid, :email, '91', :mobile, 'IN', :pin, 'user',
                     'Active', now(), now())
                """
            ),
            {
                "uid": uid,
                "email": f"test-{uid.lower()}@example.com",
                "mobile": 919900000100 + i,
                "pin": TEST_PINCODE,
            },
        )

    # One fungal/medium diagnosis per reporter, dated "now" so it's
    # well inside the 7-day detection window.
    for uid in REPORTER_IDS:
        await session.execute(
            text(
                """
                INSERT INTO plant_diagnostics
                    (diagnostic_id, user_id, plant_classification, disease_name,
                     infection_type, severity, prediction_source,
                     add_date, modify_date, status)
                VALUES
                    (:did, :uid, 'Tomato', 'Late blight',
                     :it, 'medium', 'plantvit',
                     now(), now(), 'Active')
                """
            ),
            {"did": uuid.uuid4(), "uid": uid, "it": TEST_INFECTION},
        )

    await session.commit()


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        # 1. Clean any stale test rows so the run starts fresh.
        async with Session() as s:
            await cleanup(s)

        # 2. Seed reporters + audience + diagnoses.
        async with Session() as s:
            await seed(s)
        print(
            f"Seeded {len(REPORTER_IDS)} reporters + {len(AUDIENCE_IDS)} "
            f"audience in pincode {TEST_PINCODE}"
        )

        # 3. Fire the cron.
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                CRON_URL, headers={"X-Cron-Secret": CRON_SECRET}
            )
            r.raise_for_status()
            response = r.json()
        print("Cron response:")
        print("  " + json.dumps(response, indent=2).replace("\n", "\n  "))

        # 4. Show what landed in outbreak_alerts.
        async with Session() as s:
            rows = (
                await s.execute(
                    text(
                        "SELECT user_id, pincode, infection_type, report_count "
                        "FROM outbreak_alerts WHERE user_id = ANY(:ids) "
                        "ORDER BY notified_at DESC"
                    ),
                    {"ids": ALL_TEST_IDS},
                )
            ).mappings().all()
        if rows:
            print("\nAlerts recorded:")
            for row in rows:
                print(f"  {dict(row)}")
        else:
            print("\nNo alerts recorded (audience may have been empty).")

    finally:
        # Always clean up, even on partial failure.
        async with Session() as s:
            await cleanup(s)
        print("\nCleanup done. No test artefacts remain in prod.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
