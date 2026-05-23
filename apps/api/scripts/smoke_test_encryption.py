"""End-to-end smoke test for PII encryption.

What we're proving:

  1. Writing a User row via the ORM causes ``EncryptedString``-wrapped
     columns to land in the DB as Fernet ciphertext (not the
     plaintext we passed in).
  2. Reading the same row back via the ORM transparently decrypts —
     the application code sees the original plaintext without doing
     anything explicit.
  3. ``user_email`` and ``mobile_no`` remain plaintext (so the OTP
     sign-in flow's equality lookups still work).
  4. Re-saving an already-encrypted row doesn't double-encrypt
     (process_bind_param sees the decrypted value from the prior
     load, not the ciphertext).

Run with (from ``apps/api``)::

    python scripts/smoke_test_encryption.py

The script connects to whatever DATABASE_URL is in your env. It
inserts a row with a deterministic test user_id, asserts the
properties above, then cleans up. Safe to re-run.
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.users.models import User

TEST_USER_ID = "SMOKETST01"
TEST_ADDRESS = "Village Khairabad, Tehsil Maner, District Patna"
TEST_CITY = "Patna"
TEST_STATE = "Bihar"
TEST_CROPS = "Tomato, Brinjal, Chilli"
TEST_FARM_SIZE = "2 acres"


def _ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    sys.exit(1)


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print(f"\nUsing DATABASE_URL: {settings.database_url}\n")

    # --- Clean slate ---
    async with Session() as s:
        await s.execute(
            text("DELETE FROM users WHERE user_id = :uid"),
            {"uid": TEST_USER_ID},
        )
        await s.commit()

    # --- 1. Write via ORM (triggers process_bind_param → encrypt) ---
    print("[1] Insert user via ORM…")
    async with Session() as s:
        u = User(
            user_id=TEST_USER_ID,
            user_name="Smoke Test",
            user_email="smoke@test.local",
            isd_code="91",
            mobile_no=919999900001,
            address=TEST_ADDRESS,
            city=TEST_CITY,
            state=TEST_STATE,
            country="IN",
            default_crop_interest=TEST_CROPS,
            farm_size=TEST_FARM_SIZE,
            geo_lat=Decimal("25.594095"),
            geo_lng=Decimal("85.137566"),
        )
        s.add(u)
        await s.commit()
    _ok("INSERT completed without error")

    # --- 2. Raw SQL: DB should hold ciphertext for encrypted cols,
    #         plaintext for the rest. ---
    print("\n[2] Inspect raw DB values…")
    async with Session() as s:
        row = (
            await s.execute(
                text(
                    """
                    SELECT address, city, state, default_crop_interest,
                           farm_size, user_email, mobile_no
                      FROM users
                     WHERE user_id = :uid
                    """
                ),
                {"uid": TEST_USER_ID},
            )
        ).mappings().one()

    for col, plaintext in [
        ("address", TEST_ADDRESS),
        ("city", TEST_CITY),
        ("state", TEST_STATE),
        ("default_crop_interest", TEST_CROPS),
        ("farm_size", TEST_FARM_SIZE),
    ]:
        raw = row[col]
        if not raw.startswith("gAAAAA"):
            _fail(f"{col}: raw DB value is not a Fernet token: {raw!r}")
        if plaintext in raw:
            _fail(f"{col}: plaintext leaked into raw DB value!")
        _ok(f"{col}: ciphertext stored ({len(raw)} chars, starts with gAAAAA)")

    if row["user_email"] != "smoke@test.local":
        _fail(f"user_email should be plaintext, got {row['user_email']!r}")
    _ok("user_email stored as plaintext (required for OTP lookup)")

    if row["mobile_no"] != 919999900001:
        _fail(f"mobile_no should be plaintext bigint, got {row['mobile_no']!r}")
    _ok("mobile_no stored as plaintext bigint")

    # --- 3. ORM read → transparent decrypt ---
    print("\n[3] Read user back via ORM…")
    async with Session() as s:
        u2 = (
            await s.execute(
                text("SELECT * FROM users WHERE user_id = :uid"),
                {"uid": TEST_USER_ID},
            )
        ).mappings().one()
        # That's the raw read. Now go through the ORM properly:
        from sqlalchemy import select

        u3 = (
            await s.execute(select(User).where(User.user_id == TEST_USER_ID))
        ).scalar_one()

    if u3.address != TEST_ADDRESS:
        _fail(f"address mismatch: got {u3.address!r}")
    if u3.city != TEST_CITY:
        _fail(f"city mismatch: got {u3.city!r}")
    if u3.state != TEST_STATE:
        _fail(f"state mismatch: got {u3.state!r}")
    if u3.default_crop_interest != TEST_CROPS:
        _fail(f"crops mismatch: got {u3.default_crop_interest!r}")
    if u3.farm_size != TEST_FARM_SIZE:
        _fail(f"farm_size mismatch: got {u3.farm_size!r}")
    _ok("ORM transparently decrypts all PII fields on read")

    # --- 4. Update the row → no double-encryption ---
    print("\n[4] Update a non-encrypted field, ensure encrypted ones aren't re-encrypted into ciphertext-of-ciphertext…")
    async with Session() as s:
        u4 = (
            await s.execute(select(User).where(User.user_id == TEST_USER_ID))
        ).scalar_one()
        u4.user_name = "Smoke Test (updated)"
        await s.commit()

    async with Session() as s:
        u5 = (
            await s.execute(select(User).where(User.user_id == TEST_USER_ID))
        ).scalar_one()
    if u5.address != TEST_ADDRESS:
        _fail(f"address corrupted after update: got {u5.address!r}")
    _ok("Re-save preserves PII roundtrip (no double-encryption)")

    # --- 5. Legacy plaintext fallback ---
    print("\n[5] Inject a legacy plaintext row, ensure ORM read still works…")
    async with Session() as s:
        await s.execute(
            text(
                "UPDATE users SET city = :pt WHERE user_id = :uid"
            ),
            {"pt": "Mumbai", "uid": TEST_USER_ID},
        )
        await s.commit()
    async with Session() as s:
        u6 = (
            await s.execute(select(User).where(User.user_id == TEST_USER_ID))
        ).scalar_one()
    if u6.city != "Mumbai":
        _fail(f"plaintext fallback failed: got {u6.city!r}")
    _ok("Legacy plaintext row reads back unchanged")

    # --- Cleanup ---
    async with Session() as s:
        await s.execute(
            text("DELETE FROM users WHERE user_id = :uid"),
            {"uid": TEST_USER_ID},
        )
        await s.commit()

    await engine.dispose()
    print("\n[OK] All encryption invariants verified.\n")


if __name__ == "__main__":
    asyncio.run(main())
