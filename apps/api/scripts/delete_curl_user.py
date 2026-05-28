"""One-off cleanup: delete the CURLTEST01 row from whatever DATABASE_URL points at."""
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings


async def main() -> None:
    eng = create_async_engine(get_settings().database_url)
    async with eng.begin() as conn:
        r = await conn.execute(
            text("DELETE FROM users WHERE user_id = 'CURLTEST01' RETURNING user_id")
        )
        print(f"Deleted {r.rowcount} row(s)")
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
