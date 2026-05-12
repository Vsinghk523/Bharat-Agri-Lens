import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.models import ChatMessage, ChatSession
from app.chat.schemas import (
    ChatMessageCreate,
    ChatMessageRead,
    ChatSessionCreate,
    ChatSessionRead,
)
from app.common.errors import NotFoundError
from app.db import get_session

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/sessions", response_model=ChatSessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: ChatSessionCreate, session: AsyncSession = Depends(get_session)
) -> ChatSession:
    obj = ChatSession(
        user_id="00000000",  # TODO: current_user
        title=payload.title,
        language=payload.language,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


@router.get("/sessions", response_model=list[ChatSessionRead])
async def list_sessions(
    limit: int = 50, offset: int = 0, session: AsyncSession = Depends(get_session)
) -> list[ChatSession]:
    stmt = (
        select(ChatSession)
        .where(ChatSession.deleted_at.is_(None))
        .order_by(ChatSession.add_date.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageRead])
async def list_messages(
    session_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id, ChatMessage.deleted_at.is_(None))
        .order_by(ChatMessage.add_date.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.post("/messages", response_model=ChatMessageRead, status_code=status.HTTP_201_CREATED)
async def post_message(
    payload: ChatMessageCreate, session: AsyncSession = Depends(get_session)
) -> ChatMessage:
    msg = ChatMessage(
        session_id=payload.session_id,
        role=payload.role,
        language=payload.language,
        content_text=payload.content_text,
        audio_blob_url=payload.audio_blob_url,
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_session(
    session_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> None:
    obj = await session.get(ChatSession, session_id)
    if not obj or obj.deleted_at is not None:
        raise NotFoundError("ChatSession")
    obj.status = "Inactive"
    obj.deleted_at = datetime.now(UTC)
    await session.commit()
