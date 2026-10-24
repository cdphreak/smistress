from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability import service as avail_svc
from app.backlog import service as backlog_svc
from app.config import Settings
from app.db.session import get_session
from app.llm.factory import build_provider
from app.llm.provider import LLMProvider
from app.schemas.backlog import SettlementOut

router = APIRouter(tags=["backlog"])

# Re-declared here (not imported from app.main) to avoid an import cycle.
_settings = Settings()


def get_provider() -> LLMProvider:
    return build_provider(_settings)


@router.post("/profile/{profile_id}/backlog/settle", response_model=SettlementOut)
async def settle(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    provider: LLMProvider = Depends(get_provider),
) -> SettlementOut:
    """Manual settle beat: drain the memory outbox, then judge queued media proofs."""
    if not await avail_svc.is_online(session):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The Mistress is away — nothing to settle.",
        )
    summary = await backlog_svc.settle_backlog(
        session, profile_id, provider=provider, settings=_settings,
    )
    await session.commit()
    return SettlementOut.model_validate(summary)
