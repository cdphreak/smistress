from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability import service as avail_svc
from app.chat import service as chat_svc
from app.config import Settings
from app.db.session import get_session
from app.economy import service as econ_svc
from app.llm.factory import build_provider
from app.llm.provider import LLMProvider
from app.memory.store import MemoryStore, build_memory_store
from app.schemas.chat import ChatPost, DossierOut, MessageOut
from app.services import profile as profile_svc

router = APIRouter(prefix="/profile", tags=["chat"])

# Re-declared here (not imported from app.main) to avoid an import cycle.
_settings = Settings()


def get_provider() -> LLMProvider:
    return build_provider(_settings)


def get_memory_store() -> MemoryStore:
    return build_memory_store(_settings)


async def require_llm_online(session: AsyncSession = Depends(get_session)) -> None:
    """Live chat needs her present (Addendum B2/B8). Offline -> 503; later milestones
    route offline turns to the drones instead."""
    if not await avail_svc.is_online(session):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The Mistress is away — an audience requires her presence.",
        )


def _not_found(profile_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"profile {profile_id} not found"
    )


@router.post("/{profile_id}/chat", response_model=MessageOut)
async def post_chat(
    profile_id: uuid.UUID,
    body: ChatPost,
    session: AsyncSession = Depends(get_session),
    provider: LLMProvider = Depends(get_provider),
    store: MemoryStore = Depends(get_memory_store),
    _: None = Depends(require_llm_online),
) -> MessageOut:
    try:
        reply = await chat_svc.post_message(session, profile_id, body.content, provider, store)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return MessageOut.model_validate(reply)


@router.get("/{profile_id}/messages", response_model=list[MessageOut])
async def list_messages(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[MessageOut]:
    try:
        await profile_svc.get_profile(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    msgs = await chat_svc.list_messages(session, profile_id)
    return [MessageOut.model_validate(m) for m in msgs]


@router.get("/{profile_id}/dossier", response_model=DossierOut)
async def dossier(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> DossierOut:
    try:
        data = await chat_svc.build_dossier(session, profile_id)
    except (profile_svc.ProfileNotFound, econ_svc.EconomyNotFound):
        raise _not_found(profile_id)
    return DossierOut.model_validate(data)
