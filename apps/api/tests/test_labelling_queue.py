"""Labelling-queue endpoint + reviewer-correction tests."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.models import PlantDiagnostic
from app.uploads.models import ImageUpload
from app.users.models import User


async def _seed(
    db_session: AsyncSession,
    user_id: str,
    *,
    feedback: str | None,
    plant: str = "Tomato",
    disease: str = "Late blight",
) -> PlantDiagnostic:
    user = await db_session.get(User, user_id)
    if user is None:
        user = User(
            user_id=user_id,
            user_email=f"{user_id.lower()}@labels.example.com",
            user_type="Farmer",
        )
        db_session.add(user)
        await db_session.commit()

    img = ImageUpload(
        image_id=uuid.uuid4(),
        user_id=user_id,
        image_name=f"{user_id}.jpg",
        image_file_type="jpeg",
        storage_location=f"uploads/{user_id}/{uuid.uuid4()}.jpg",
        mime_type="image/jpeg",
    )
    db_session.add(img)
    await db_session.commit()

    diag = PlantDiagnostic(
        user_id=user_id,
        image_id=img.image_id,
        plant_classification=plant,
        disease_name=disease,
        infection_type="fungal",
        user_feedback=feedback,
    )
    db_session.add(diag)
    await db_session.commit()
    return diag


async def test_labelling_queue_returns_only_flagged(
    client: AsyncClient,
    authed_admin: tuple[str, dict[str, str]],
    db_session: AsyncSession,
) -> None:
    """Rows where user_feedback is null or 'correct' are excluded;
    'incorrect' and 'partial' rows surface in the queue."""
    _, headers = authed_admin
    await _seed(db_session, "LBL0000001", feedback="incorrect")
    await _seed(db_session, "LBL0000002", feedback="partial")
    await _seed(db_session, "LBL0000003", feedback="correct")  # excluded
    await _seed(db_session, "LBL0000004", feedback=None)  # excluded

    r = await client.get("/admin/labelling-queue", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    verdicts = {item["user_feedback"] for item in body["items"]}
    assert verdicts == {"incorrect", "partial"}
    # Predicted labels round-trip.
    plants = {item["predicted_plant"] for item in body["items"]}
    assert plants == {"Tomato"}


async def test_labelling_queue_paginates(
    client: AsyncClient,
    authed_admin: tuple[str, dict[str, str]],
    db_session: AsyncSession,
) -> None:
    """``total`` reflects the unpaginated count, ``items`` respects
    ``limit`` / ``offset``."""
    _, headers = authed_admin
    for i in range(5):
        await _seed(
            db_session, f"PAGE{i:04d}1", feedback="incorrect", plant=f"Crop{i}"
        )

    r1 = await client.get("/admin/labelling-queue?limit=2&offset=0", headers=headers)
    r2 = await client.get("/admin/labelling-queue?limit=2&offset=2", headers=headers)
    r3 = await client.get("/admin/labelling-queue?limit=2&offset=4", headers=headers)

    for r in (r1, r2, r3):
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 5

    assert len(r1.json()["items"]) == 2
    assert len(r2.json()["items"]) == 2
    assert len(r3.json()["items"]) == 1


async def test_labelling_queue_requires_token(client: AsyncClient) -> None:
    r = await client.get("/admin/labelling-queue")
    assert r.status_code == 401


async def test_labelling_queue_forbids_non_admin(
    client: AsyncClient,
    authed_user: tuple[str, dict[str, str]],
) -> None:
    """A regular user with a valid token still gets 403 — they
    identified themselves successfully but lack the admin role."""
    _, headers = authed_user
    r = await client.get("/admin/labelling-queue", headers=headers)
    assert r.status_code == 403


async def test_correct_diagnostic_stamps_reviewer(
    client: AsyncClient,
    authed_admin: tuple[str, dict[str, str]],
    db_session: AsyncSession,
) -> None:
    """PATCH applies the reviewer's correction and stamps reviewed_by
    / reviewed_at server-side. The original predicted_* columns stay
    untouched."""
    admin_id, headers = authed_admin
    diag = await _seed(db_session, "REV0000001", feedback="incorrect", plant="Tomato")

    r = await client.patch(
        f"/admin/labelling-queue/{diag.diagnostic_id}",
        headers=headers,
        json={
            "correct_plant": "Potato",
            "correct_disease": "Early blight",
            "correct_infection_type": "fungal",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["correct_plant"] == "Potato"
    assert body["correct_disease"] == "Early blight"
    assert body["correct_infection_type"] == "fungal"
    assert body["reviewed_by"] == admin_id
    assert body["reviewed_at"] is not None
    # Predicted fields are kept for audit / error-analysis.
    assert body["predicted_plant"] == "Tomato"

    await db_session.refresh(diag)
    assert diag.correct_plant == "Potato"
    assert diag.reviewed_by == admin_id
    assert diag.plant_classification == "Tomato"  # NOT mutated


async def test_correct_diagnostic_forbids_non_admin(
    client: AsyncClient,
    authed_user: tuple[str, dict[str, str]],
    db_session: AsyncSession,
) -> None:
    _, headers = authed_user
    diag = await _seed(db_session, "REV0000002", feedback="incorrect")
    r = await client.patch(
        f"/admin/labelling-queue/{diag.diagnostic_id}",
        headers=headers,
        json={"correct_plant": "Potato"},
    )
    assert r.status_code == 403


async def test_correct_diagnostic_404_for_missing(
    client: AsyncClient,
    authed_admin: tuple[str, dict[str, str]],
) -> None:
    _, headers = authed_admin
    r = await client.patch(
        f"/admin/labelling-queue/{uuid.uuid4()}",
        headers=headers,
        json={"correct_plant": "Anything"},
    )
    assert r.status_code == 404


async def test_admin_can_purge_other_user(
    client: AsyncClient,
    authed_admin: tuple[str, dict[str, str]],
    db_session: AsyncSession,
) -> None:
    """Admins can DPDP-purge any account; regular users can only purge
    themselves. Self-purge tests live elsewhere — this one covers the
    role-based half of the new admin gate."""
    _, headers = authed_admin
    victim = User(
        user_id="VICTIM0001",
        user_email="victim@purge.example.com",
        user_type="Farmer",
    )
    db_session.add(victim)
    await db_session.commit()

    r = await client.delete("/users/VICTIM0001/purge", headers=headers)
    assert r.status_code == 204

    # Victim row is gone.
    assert await db_session.get(User, "VICTIM0001") is None


async def test_non_admin_cannot_purge_other_user(
    client: AsyncClient,
    authed_user: tuple[str, dict[str, str]],
    db_session: AsyncSession,
) -> None:
    """A regular user must NOT be able to purge someone else's account.
    The endpoint returns 401 (kept for backwards-compat with the
    earlier self-only behaviour); the relevant assertion is that the
    target user is still there afterwards."""
    _, headers = authed_user
    other = User(
        user_id="SAFEEE0001",
        user_email="safe@purge.example.com",
        user_type="Farmer",
    )
    db_session.add(other)
    await db_session.commit()

    r = await client.delete("/users/SAFEEE0001/purge", headers=headers)
    assert r.status_code in (401, 403)
    assert await db_session.get(User, "SAFEEE0001") is not None
