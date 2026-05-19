from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.services.bhashini import to_bhashini_lang
from app.services.translation import get_translator
from app.translations.schemas import TranslateRequest, TranslateResponse
from app.users.models import User

router = APIRouter(prefix="/translate", tags=["translations"])


@router.post("", response_model=TranslateResponse)
async def translate(
    payload: TranslateRequest,
    _: User = Depends(get_current_user),
) -> TranslateResponse:
    """Translate arbitrary text via the configured provider.

    Provider is selected by ``TRANSLATION_PROVIDER`` env var (google,
    bhashini, mock, or auto). Gated behind the standard Bearer auth so
    the rate-limited / paid provider quota can't be drained by anonymous
    traffic.
    """
    translator = get_translator()
    src = to_bhashini_lang(payload.source_language)
    tgt = to_bhashini_lang(payload.target_language)
    translated = await translator.translate(payload.text, src, tgt)
    return TranslateResponse(
        text=translated,
        source_language=payload.source_language,
        target_language=payload.target_language,
        provider="mock" if translator.mock_mode else translator.provider,
    )
