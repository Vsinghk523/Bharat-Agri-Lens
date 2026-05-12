from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.services.bhashini import get_bhashini_client, to_bhashini_lang
from app.translations.schemas import TranslateRequest, TranslateResponse
from app.users.models import User

router = APIRouter(prefix="/translate", tags=["translations"])


@router.post("", response_model=TranslateResponse)
async def translate(
    payload: TranslateRequest,
    _: User = Depends(get_current_user),
) -> TranslateResponse:
    """Translate arbitrary text via Bhashini (mock or real).

    Gated behind the standard Bearer auth so the rate-limited Bhashini
    quota can't be drained by anonymous traffic.
    """
    client = get_bhashini_client()
    src = to_bhashini_lang(payload.source_language)
    tgt = to_bhashini_lang(payload.target_language)
    translated = await client.translate(payload.text, src, tgt)
    return TranslateResponse(
        text=translated,
        source_language=payload.source_language,
        target_language=payload.target_language,
        provider="mock" if client.mock_mode else "bhashini",
    )
