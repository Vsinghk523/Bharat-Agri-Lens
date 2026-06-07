r"""Make the 'In your area' panel visible on YOUR Home page.

Trigger #3's outbreak alert panel renders only when an
``outbreak_alerts`` row exists for the current user. By design the
detection cron *excludes* reporters (you can't be the audience for
your own outbreak), so a real farmer who diagnosed the disease never
sees an alert about it -- which is correct in prod but inconvenient
for demoing the UI.

This script forces a row to exist so you can see the panel render,
then lets you clean up with a single flag.

Usage
-----
    cd apps/api
    $env:DATABASE_URL = "postgresql+asyncpg://...turntable.proxy.rlwy.net:35980/railway"

    # Insert demo row, then refresh Home in browser / APK:
    .\.venv\Scripts\python.exe scripts\demo_outbreak_panel.py

    # When done, remove the demo row (idempotent):
    .\.venv\Scripts\python.exe scripts\demo_outbreak_panel.py --clean

Defaults
--------
- ``TARGET_USER_ID = "1E2597891F"`` -- Vivek's account
- ``TARGET_PINCODE = "411001"``
- ``TARGET_INFECTION = "fungal"``
- ``TARGET_REPORT_COUNT = 6``
- ``week_key`` is the current ISO week (matches what the cron would write)

Change ``TARGET_USER_ID`` at the top if you want to demo a different
account. The script also patches the user's ``pincode`` to 411001 if
it isn't already set, so the Home panel's secondary condition
(``me.pincode`` non-null) is satisfied.

Safety
------
- Inserts AT MOST one row (UNIQUE constraint on
  ``(user_id, pincode, infection_type, week_key)``)
- ``--clean`` deletes that exact row -- no broader scan, no other
  users' data touched
- The row is dated "now()" so the GET /users/me/outbreak-alerts
  14-day window catches it

ASCII-only output: Windows default cp1252 can't encode arrows /
em-dashes, and we'd rather the script stay portable than print pretty.
"""
from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings

TARGET_USER_ID = "1E2597891F"
TARGET_PINCODE = "411001"
TARGET_INFECTION = "fungal"
TARGET_REPORT_COUNT = 6


def _current_week_key() -> str:
    """Same format the production cron uses: ISO ``YYYY-Www``."""
    iso = datetime.now(UTC).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


async def ensure_pincode(session) -> None:
    """Set the user's pincode to 411001 if it's currently null/empty.

    Idempotent -- if pincode is already 411001 (or any value) we leave
    it alone. The Home panel only renders when ``me.pincode`` is
    non-null, so this guarantees the second condition is satisfied.
    """
    row = (
        await session.execute(
            text("SELECT pincode FROM users WHERE user_id = :uid"),
            {"uid": TARGET_USER_ID},
        )
    ).first()
    if not row:
        raise RuntimeError(
            f"User {TARGET_USER_ID} not found -- check TARGET_USER_ID at "
            "the top of this script."
        )
    existing = (row[0] or "").strip()
    if existing == TARGET_PINCODE:
        print(f"  pincode already = {TARGET_PINCODE} (no change)")
        return
    if existing:
        print(
            f"  pincode is currently {existing!r} -- leaving it alone. "
            "If the panel doesn't appear, set it to 411001 from the "
            "Profile page first."
        )
        return
    await session.execute(
        text("UPDATE users SET pincode = :pin WHERE user_id = :uid"),
        {"pin": TARGET_PINCODE, "uid": TARGET_USER_ID},
    )
    await session.commit()
    print(f"  pincode was null -> set to {TARGET_PINCODE}")


async def insert_demo_row(session) -> None:
    week_key = _current_week_key()
    alert_id = uuid.uuid4()
    notified_at = datetime.now(UTC)
    # ON CONFLICT DO NOTHING handles the case where the user runs the
    # script twice in the same ISO week -- the UNIQUE constraint would
    # otherwise raise, and we'd rather quietly no-op.
    await session.execute(
        text(
            """
            INSERT INTO outbreak_alerts
                (alert_id, user_id, pincode, infection_type, week_key,
                 notified_at, report_count)
            VALUES
                (:aid, :uid, :pin, :it, :wk, :ts, :rc)
            ON CONFLICT (user_id, pincode, infection_type, week_key)
            DO NOTHING
            """
        ),
        {
            "aid": alert_id,
            "uid": TARGET_USER_ID,
            "pin": TARGET_PINCODE,
            "it": TARGET_INFECTION,
            "wk": week_key,
            "ts": notified_at,
            "rc": TARGET_REPORT_COUNT,
        },
    )
    await session.commit()
    print(
        f"  inserted/kept 1 row: user={TARGET_USER_ID} pincode={TARGET_PINCODE} "
        f"infection={TARGET_INFECTION} count={TARGET_REPORT_COUNT} "
        f"week={week_key}"
    )


async def delete_demo_rows(session) -> None:
    """Remove the demo row(s). Targeted delete -- only the exact
    (user, pincode, infection) triple from this script can match."""
    result = await session.execute(
        text(
            """
            DELETE FROM outbreak_alerts
            WHERE user_id = :uid
              AND pincode = :pin
              AND infection_type = :it
            """
        ),
        {
            "uid": TARGET_USER_ID,
            "pin": TARGET_PINCODE,
            "it": TARGET_INFECTION,
        },
    )
    await session.commit()
    print(f"  deleted {result.rowcount} row(s) for {TARGET_USER_ID}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove the demo row instead of inserting one.",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    if args.clean:
        print(f"Cleaning demo outbreak_alerts row for {TARGET_USER_ID}...")
        async with Session() as s:
            await delete_demo_rows(s)
        print("Done. Refresh Home -- the panel should disappear.")
    else:
        print(f"Inserting demo outbreak_alerts row for {TARGET_USER_ID}...")
        async with Session() as s:
            await ensure_pincode(s)
            await insert_demo_row(s)
        print(
            "\nDone. Refresh Home (or kill + reopen the app) -- the "
            "saffron 'In your area / 411001' panel should now appear "
            "between MY CROPS and RECENT DIAGNOSES.\n"
            "\nWhen you're done, clean up with:\n"
            "  .\\.venv\\Scripts\\python.exe scripts\\demo_outbreak_panel.py --clean"
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
