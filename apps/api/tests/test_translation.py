"""Bhashini translation tests (mock mode)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.models import DiagnosticFollowupQuestion, PlantDiagnostic
from app.uploads.models import ImageUpload


async def test_translate_endpoint_mock_mode(
    client: AsyncClient, authed_user: tuple[str, dict[str, str]]
) -> None:
    """Without Bhashini creds the endpoint returns a deterministic
    pseudo-translation and reports provider=mock."""
    _, headers = authed_user
    r = await client.post(
        "/translate",
        headers=headers,
        json={
            "text": "Tomato",
            "source_language": "en-IN",
            "target_language": "hi-IN",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "mock"
    assert body["text"] == "hi «Tomato»"  # the deterministic mock format
    assert body["source_language"] == "en-IN"
    assert body["target_language"] == "hi-IN"


async def test_translate_skips_same_language(
    client: AsyncClient, authed_user: tuple[str, dict[str, str]]
) -> None:
    """en → en is a no-op even in mock mode."""
    _, headers = authed_user
    r = await client.post(
        "/translate",
        headers=headers,
        json={
            "text": "Tomato",
            "source_language": "en-IN",
            "target_language": "en-IN",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "Tomato"


async def test_translate_requires_token(client: AsyncClient) -> None:
    """The endpoint shares the standard Bearer guard."""
    r = await client.post(
        "/translate",
        json={"text": "x", "target_language": "hi-IN"},
    )
    assert r.status_code == 401


async def _seed_user_and_diagnostic(
    db_session: AsyncSession, user_id: str, preferred_language: str = "en-IN"
) -> PlantDiagnostic:
    """Helper: insert a user + image + diagnostic; return the diagnostic."""
    from app.users.models import User

    user = User(
        user_id=user_id,
        user_email=f"{user_id.lower()}@translation.example.com",
        user_type="Farmer",
        preferred_language=preferred_language,
    )
    db_session.add(user)
    await db_session.commit()

    img = ImageUpload(
        image_id=uuid.uuid4(),
        user_id=user_id,
        image_name="a.jpg",
        image_file_type="jpeg",
        storage_location=f"uploads/{user_id}/a.jpg",
        mime_type="image/jpeg",
    )
    db_session.add(img)
    await db_session.commit()

    diag = PlantDiagnostic(
        user_id=user_id,
        image_id=img.image_id,
        plant_classification="Tomato",
        scientific_name="Solanum lycopersicum",
        disease_name="Late blight",
        infection_type="fungal",
        suggested_remedies="Spray neem oil weekly.",
        preventive_measures="Rotate crops.",
        language_used=preferred_language,
    )
    db_session.add(diag)
    await db_session.commit()
    return diag


async def test_get_diagnostic_translates_for_hindi_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /diagnostics/{id} translates user-facing text when the
    caller's preferred_language is non-English. Technical fields
    (scientific_name, infection_type) are left alone."""
    from app.auth.service import issue_tokens

    diag = await _seed_user_and_diagnostic(
        db_session, "TRA0000001", preferred_language="hi-IN"
    )
    access, _ = issue_tokens("TRA0000001")
    headers = {"Authorization": f"Bearer {access}"}

    r = await client.get(f"/diagnostics/{diag.diagnostic_id}", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # User-facing fields are translated via the mock prefix format.
    assert body["plant_classification"] == "hi «Tomato»"
    assert body["disease_name"] == "hi «Late blight»"
    assert body["suggested_remedies"] == "hi «Spray neem oil weekly.»"
    assert body["preventive_measures"] == "hi «Rotate crops.»"
    # Technical / language-neutral fields stay as-is.
    assert body["scientific_name"] == "Solanum lycopersicum"
    assert body["infection_type"] == "fungal"

    # The DB row was NOT mutated — it's still canonical English.
    await db_session.refresh(diag)
    assert diag.plant_classification == "Tomato"
    assert diag.disease_name == "Late blight"


async def test_get_diagnostic_no_translation_for_english_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """English users see the bytes that came out of the inference
    service — no prefix, no mutation."""
    from app.auth.service import issue_tokens

    diag = await _seed_user_and_diagnostic(
        db_session, "TRA0000002", preferred_language="en-IN"
    )
    access, _ = issue_tokens("TRA0000002")
    headers = {"Authorization": f"Bearer {access}"}

    r = await client.get(f"/diagnostics/{diag.diagnostic_id}", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plant_classification"] == "Tomato"
    assert body["disease_name"] == "Late blight"


async def test_followups_list_translates_for_hindi_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.auth.service import issue_tokens

    diag = await _seed_user_and_diagnostic(
        db_session, "TRA0000003", preferred_language="hi-IN"
    )
    db_session.add(
        DiagnosticFollowupQuestion(
            diagnostic_id=diag.diagnostic_id,
            question_text="What is the safe dose?",
            question_language="en-IN",
            category="dosage",
            display_order=0,
        )
    )
    await db_session.commit()

    access, _ = issue_tokens("TRA0000003")
    r = await client.get(
        f"/diagnostics/{diag.diagnostic_id}/followups",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    assert body[0]["question_text"] == "hi «What is the safe dose?»"
