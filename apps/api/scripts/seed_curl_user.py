"""Seed a test user + print a JWT for curl-based endpoint testing.

The OTP flow needs real Resend/WhatsApp delivery; this short-circuits
it by inserting a row directly and minting a token via the same
``issue_tokens`` helper the API uses. Output goes to stdout in a
shell-parseable form so the calling script can grab the token.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.auth.service import issue_tokens
from app.config import get_settings
from app.users.models import User

TEST_USER_ID = "CURLTEST01"


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as s:
        # Clean slate so re-runs work.
        await s.execute(
            text("DELETE FROM users WHERE user_id = :uid"),
            {"uid": TEST_USER_ID},
        )
        await s.commit()

        u = User(
            user_id=TEST_USER_ID,
            user_name="Curl Test",
            user_email="curl-test@example.com",
            isd_code="91",
            mobile_no=919999900099,
            country="IN",
        )
        s.add(u)
        await s.commit()

    access, _refresh = issue_tokens(TEST_USER_ID)
    await engine.dispose()

    # Print in a form PowerShell can capture easily.
    print(f"USER_ID={TEST_USER_ID}")
    print(f"ACCESS={access}")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
