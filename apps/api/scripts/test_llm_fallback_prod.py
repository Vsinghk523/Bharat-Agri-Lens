"""End-to-end smoke test of the LLM-fallback pipeline against prod.

1. Seed a test user (against prod DB via DATABASE_PUBLIC_URL).
2. Mint a JWT.
3. Upload a non-target-plant image via /uploads/direct.
4. POST /diagnostics with the resulting image_id.
5. Print the response so we can verify prediction_source='llm_fallback'.

Run with:
    cd apps/api
    # Set DATABASE_URL + JWT_SECRET + CPA_FERNET_KEY from railway:
    .\.venv\Scripts\python.exe scripts\test_llm_fallback_prod.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.service import issue_tokens  # noqa: E402

API_BASE = "https://api-production-d64e.up.railway.app"
TEST_USER = "FALLBKTEST"
# A rose photo — should trip CLIP's non_target_plant gate, then route
# to Gemini via the LLM fallback.
TEST_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/8/89/Tomato_je.jpg"


async def _seed_user() -> None:
    """Insert the test user into prod DB."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.config import get_settings

    eng = create_async_engine(get_settings().database_url)
    async with eng.begin() as conn:
        await conn.execute(
            text("DELETE FROM users WHERE user_id = :uid"), {"uid": TEST_USER}
        )
        await conn.execute(
            text(
                "INSERT INTO users (user_id, user_email, isd_code, mobile_no, country) "
                "VALUES (:uid, :email, '91', 919999900112, 'IN')"
            ),
            {"uid": TEST_USER, "email": "fallback-test@example.com"},
        )
    await eng.dispose()


def _fetch_image() -> bytes:
    req = Request(
        TEST_IMAGE_URL,
        headers={"User-Agent": "bal-fallback-test/1.0 (admin@bharatagrilens.in)"},
    )
    with urlopen(req) as r:  # noqa: S310
        return r.read()


async def main() -> None:
    print("Seeding test user...")
    await _seed_user()

    token, _ = issue_tokens(TEST_USER)
    auth_headers = {"Authorization": f"Bearer {token}"}
    print(f"Test user: {TEST_USER}")

    print(f"\nFetching test image from {TEST_IMAGE_URL}...")
    img = _fetch_image()
    print(f"  {len(img)} bytes")

    async with httpx.AsyncClient(timeout=120.0) as client:
        print("\nUploading via /uploads/direct...")
        files = {"file": ("test.jpg", img, "image/jpeg")}
        r = await client.post(
            f"{API_BASE}/uploads/direct",
            headers=auth_headers,
            files=files,
            params={"image_name": "rose"},
        )
        r.raise_for_status()
        upload = r.json()
        print(f"  image_id: {upload['image_id']}")

        print("\nPOST /diagnostics ...")
        r = await client.post(
            f"{API_BASE}/diagnostics",
            headers={**auth_headers, "Content-Type": "application/json"},
            json={"image_id": upload["image_id"], "language": "en-IN"},
        )
        r.raise_for_status()
        diag = r.json()

    print("\n=== diagnostic response ===")
    keys_of_interest = [
        "plant_classification",
        "scientific_name",
        "disease_name",
        "infection_type",
        "severity",
        "confidence_score",
        "rejection_reason",
        "rejection_hint",
        "prediction_source",
        "model_version",
    ]
    for k in keys_of_interest:
        print(f"  {k}: {diag.get(k)}")

    if diag.get("prediction_source") == "llm_fallback":
        print("\n  ✅ Gemini LLM fallback was used end-to-end against prod!")
    elif diag.get("rejection_reason"):
        print(
            f"\n  Rejected with reason={diag['rejection_reason']}, "
            f"hint={diag.get('rejection_hint')}"
        )
    else:
        print("\n  PlantViT diagnosed it directly (no fallback needed).")


if __name__ == "__main__":
    asyncio.run(main())
