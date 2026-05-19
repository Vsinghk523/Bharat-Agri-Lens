"""Chat session + message endpoints.

POST /chat/messages is the interesting one: it round-trips a single
user turn through Bhashini (user-language ↔ English) and the
inference service (English ↔ English) so the assistant reply lands
back in the user's preferred language without losing the canonical
record in the database.
"""

import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.chat.models import ChatMessage, ChatSession
from app.chat.schemas import (
    ChatExchange,
    ChatMessageCreate,
    ChatMessageRead,
    ChatSessionCreate,
    ChatSessionRead,
)
from app.common.errors import NotFoundError
from app.config import get_settings
from app.db import get_session
from app.logging import get_logger
from app.services.bhashini import to_bhashini_lang
from app.services.translation import get_translator
from app.users.models import User

router = APIRouter(prefix="/chat", tags=["chat"])
settings = get_settings()
log = get_logger(__name__)


async def _load_user_session(
    session: AsyncSession, session_id: uuid.UUID, user_id: str
) -> ChatSession | None:
    obj = await session.get(ChatSession, session_id)
    if not obj or obj.deleted_at is not None or obj.user_id != user_id:
        return None
    return obj


async def _call_chat_inference(message: str) -> str | None:
    """POST the (English) prompt to the inference service. Returns
    ``None`` on any HTTP / parse error so the caller can degrade
    gracefully rather than 500."""
    try:
        async with httpx.AsyncClient(timeout=settings.inference_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.inference_base_url}/chat/reply",
                json={"message": message, "language": "en"},
            )
            if resp.status_code >= 400:
                log.warning("inference_chat_non_2xx", status=resp.status_code)
                return None
            payload = resp.json()
            return payload.get("reply") or None
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("inference_chat_failed", error=str(exc))
        return None


@router.post("/sessions", response_model=ChatSessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: ChatSessionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ChatSession:
    obj = ChatSession(
        user_id=current_user.user_id,
        title=payload.title,
        language=payload.language,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


@router.get("/sessions", response_model=list[ChatSessionRead])
async def list_sessions(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ChatSession]:
    stmt = (
        select(ChatSession)
        .where(
            ChatSession.deleted_at.is_(None),
            ChatSession.user_id == current_user.user_id,
        )
        .order_by(ChatSession.add_date.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageRead])
async def list_messages(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ChatMessage]:
    if not await _load_user_session(session, session_id, current_user.user_id):
        raise NotFoundError("ChatSession")
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id, ChatMessage.deleted_at.is_(None))
        .order_by(ChatMessage.add_date.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.post(
    "/messages",
    response_model=ChatExchange,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    payload: ChatMessageCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ChatExchange:
    """Full conversational turn: user message in -> assistant message out.

    Pipeline:
      1. Resolve / create the chat session.
      2. Persist the user bubble in the user's original language.
      3. Translate to English for grounding.
      4. Ask the inference service for an English reply.
      5. Translate the reply back to the user's language.
      6. Persist the assistant bubble.
      7. Return both bubbles so the client renders them in one paint.

    If the inference service is unreachable the user bubble still
    persists, ``assistant_message`` comes back null, and ``error``
    is set to "inference_unavailable" so the UI can show a useful
    fallback instead of a generic 500.
    """
    # 1. Resolve / create the session.
    if payload.session_id is not None:
        chat_session = await _load_user_session(
            session, payload.session_id, current_user.user_id
        )
        if not chat_session:
            raise NotFoundError("ChatSession")
    else:
        chat_session = ChatSession(
            user_id=current_user.user_id,
            language=payload.language,
        )
        session.add(chat_session)
        await session.flush()

    # 2. Persist the user bubble.
    user_msg = ChatMessage(
        session_id=chat_session.session_id,
        role="user",
        language=payload.language,
        content_text=payload.content_text,
    )
    session.add(user_msg)
    await session.flush()
    await session.refresh(user_msg)

    # 3. Translate user text -> English for the LLM. Implementations
    # return the input unchanged when source == target, so the en-IN
    # case is a fast no-op.
    translator = get_translator()
    src_lang = to_bhashini_lang(payload.language)
    english_prompt = await translator.translate(payload.content_text, src_lang, "en")

    # 4. Call the inference service.
    reply_en = await _call_chat_inference(english_prompt)

    if reply_en is None:
        await session.commit()
        return ChatExchange(
            session_id=chat_session.session_id,
            user_message=ChatMessageRead.model_validate(user_msg),
            assistant_message=None,
            error="inference_unavailable",
        )

    # 5. Translate the reply back to the user's language.
    reply_user_lang = await translator.translate(reply_en, "en", src_lang)

    # 6. Persist the assistant bubble.
    asst_msg = ChatMessage(
        session_id=chat_session.session_id,
        role="assistant",
        language=payload.language,
        content_text=reply_user_lang,
    )
    session.add(asst_msg)
    await session.commit()
    await session.refresh(asst_msg)

    return ChatExchange(
        session_id=chat_session.session_id,
        user_message=ChatMessageRead.model_validate(user_msg),
        assistant_message=ChatMessageRead.model_validate(asst_msg),
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_session(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    obj = await _load_user_session(session, session_id, current_user.user_id)
    if not obj:
        raise NotFoundError("ChatSession")
    obj.status = "Inactive"
    obj.deleted_at = datetime.now(UTC)
    await session.commit()
