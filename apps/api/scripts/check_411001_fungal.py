"""Quick read-only check: who has a recent fungal diagnosis at pincode 411001?

Run:
    cd apps/api
    $env:DATABASE_URL = "postgresql+asyncpg://...turntable.proxy.rlwy.net:35980/railway"
    .\.venv\Scripts\python.exe scripts\check_411001_fungal.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as ses:
        rows = (
            await ses.execute(
                text(
                    """
                    SELECT u.user_id,
                           u.user_name,
                           u.mobile_no,
                           d.disease_name,
                           d.infection_type,
                           d.severity,
                           d.add_date
                    FROM plant_diagnostics d
                    JOIN users u USING (user_id)
                    WHERE u.pincode = '411001'
                      AND d.infection_type = 'fungal'
                      AND d.add_date > now() - interval '7 days'
                    ORDER BY d.add_date DESC
                    """
                )
            )
        ).mappings().all()

    if not rows:
        print("No fungal diagnoses at pincode 411001 in the last 7 days.")
    else:
        print(f"Found {len(rows)} fungal diagnoses at pincode 411001 (last 7 days):\n")
        for r in rows:
            print(f"  {dict(r)}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
