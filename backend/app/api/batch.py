from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import get_provider, require_llm_online
from app.batch import service as batch_svc
from app.db.session import get_session
from app.llm.provider import LLMProvider
from app.schemas.batch import GenerateBatchOut, PoolStatusOut
from app.services import profile as profile_svc

router = APIRouter(prefix="/profile", tags=["batch"])


@router.post("/{profile_id}/batch/generate", response_model=GenerateBatchOut)
async def generate_batch(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    provider: LLMProvider = Depends(get_provider),
    _: None = Depends(require_llm_online),
) -> GenerateBatchOut:
    try:
        result = await batch_svc.generate_batch(session, profile_id, provider)
    except (profile_svc.ProfileNotFound, batch_svc.ProfileNotFound):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"profile {profile_id} not found"
        )
    await session.commit()
    return GenerateBatchOut(
        tasks_added=result.tasks_added,
        lines_added=result.lines_added,
        task_pool=result.task_pool,
        line_bank=result.line_bank,
    )


@router.get("/{profile_id}/batch/status", response_model=PoolStatusOut)
async def batch_status(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> PoolStatusOut:
    try:
        await profile_svc.get_profile(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"profile {profile_id} not found"
        )
    s = await batch_svc.pool_status(session, profile_id)
    return PoolStatusOut(
        task_pool=s.task_pool,
        line_bank=s.line_bank,
        task_pool_low=s.task_pool_low,
        line_bank_low=s.line_bank_low,
    )
