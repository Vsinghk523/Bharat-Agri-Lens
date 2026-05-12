"""Labelling-queue endpoint tests."""

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
    authed_user: tuple[str, dict[str, str]],
    db_session: AsyncSession,
) -> None:
    """Rows where user_feedback is null or 'correct' are excluded;
    'incorrect' and 'partial' rows surface in the queue."""
    _, headers = authed_user
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
    authed_user: tuple[str, dict[str, str]],
    db_session: AsyncSession,
) -> None:
    """``total`` reflects the unpaginated count, ``items`` respects
    ``limit`` / ``offset``."""
    _, headers = authed_user
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
