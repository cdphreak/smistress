from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.session import get_session
from app.memory import service as mem_svc
from app.memory.store import build_memory_store
from app.services import profile as profile_svc

router = APIRouter(prefix="/profile", tags=["memory"])

_settings = Settings()


@router.post("/{profile_id}/memory/seed", status_code=status.HTTP_201_CREATED)
async def seed_memory(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await mem_svc.seed_profile_episode(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"profile {profile_id} not found",
        )
    # best-effort drain now; anything not pushed stays queued for a later retry.
    store = build_memory_store(_settings)
    drained = await mem_svc.drain_outbox(session, store)
    await session.commit()
    return {"queued": 1, "drained": drained}
