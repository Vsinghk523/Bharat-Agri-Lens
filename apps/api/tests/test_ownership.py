"""User-A-vs-user-B isolation on diagnostics."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import issue_tokens
from app.diagnostics.models import PlantDiagnostic
from app.uploads.models import ImageUpload
from app.users.models import User


async def test_diagnostic_ownership_isolation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """User A's diagnostics must be invisible to user B."""
    user_a = User(user_id="AAAA000001", user_email="a@iso.example.com", user_type="Farmer")
    user_b = User(user_id="BBBB000001", user_email="b@iso.example.com", user_type="Farmer")
    db_session.add_all([user_a, user_b])
    await db_session.commit()

    # Insert + commit the image *first* so the PlantDiagnostic FK has a real
    # parent row to point at; doing both in a single add_all left SA free to
    # flush them in either order and triggered intermittent FK violations.
    image_id = uuid.uuid4()
    img = ImageUpload(
        image_id=image_id,
        user_id=user_a.user_id,
        image_name="a.jpg",
        image_file_type="jpeg",
        storage_location=f"uploads/{user_a.user_id}/a.jpg",
        mime_type="image/jpeg",
    )
    db_session.add(img)
    await db_session.commit()

    diag = PlantDiagnostic(
        user_id=user_a.user_id,
        image_id=image_id,
        plant_classification="Tomato",
        infection_type="fungal",
        language_used="en-IN",
    )
    db_session.add(diag)
    await db_session.commit()

    access_a, _ = issue_tokens(user_a.user_id)
    access_b, _ = issue_tokens(user_b.user_id)
    headers_a = {"Authorization": f"Bearer {access_a}"}
    headers_b = {"Authorization": f"Bearer {access_b}"}

    # User A: list shows 1 row, direct GET returns 200.
    list_a = await client.get("/diagnostics", headers=headers_a)
    assert list_a.status_code == 200
    body_a = list_a.json()
    assert len(body_a) == 1
    assert body_a[0]["plant_classification"] == "Tomato"

    get_a = await client.get(
        f"/diagnostics/{diag.diagnostic_id}", headers=headers_a
    )
    assert get_a.status_code == 200

    # User B: list is empty, direct GET returns 404 (not 403, so we don't leak existence).
    list_b = await client.get("/diagnostics", headers=headers_b)
    assert list_b.status_code == 200
    assert list_b.json() == []

    get_b = await client.get(
        f"/diagnostics/{diag.diagnostic_id}", headers=headers_b
    )
    assert get_b.status_code == 404

    # User B cannot soft-delete user A's diagnostic either.
    del_b = await client.delete(
        f"/diagnostics/{diag.diagnostic_id}", headers=headers_b
    )
    assert del_b.status_code == 404
