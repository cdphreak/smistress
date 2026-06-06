from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.economy import service as econ_svc
from app.schemas.economy import DenialTimerIn, DenialTimerOut, StandingOut, TokenOp

router = APIRouter(prefix="/profile", tags=["economy"])


def _econ_404(profile_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"economy for profile {profile_id} not found"
    )


@router.get("/{profile_id}/standing", response_model=StandingOut)
async def standing(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> StandingOut:
    try:
        econ = await econ_svc.get_economy(session, profile_id)
    except econ_svc.EconomyNotFound:
        raise _econ_404(profile_id)
    timers = await econ_svc.active_denial_timers(session, profile_id)
    return StandingOut(
        merit=econ.merit, rank=econ.rank, tokens=econ.tokens,
        denial_timers=[DenialTimerOut.model_validate(t) for t in timers],
    )


@router.post("/{profile_id}/tokens/grant", response_model=StandingOut)
async def grant_tokens(
    profile_id: uuid.UUID, body: TokenOp, session: AsyncSession = Depends(get_session)
) -> StandingOut:
    try:
        await econ_svc.grant_tokens(session, profile_id, body.amount)
    except econ_svc.EconomyNotFound:
        raise _econ_404(profile_id)
    await session.commit()
    return await standing(profile_id, session)


@router.post("/{profile_id}/tokens/spend", response_model=StandingOut)
async def spend_tokens(
    profile_id: uuid.UUID, body: TokenOp, session: AsyncSession = Depends(get_session)
) -> StandingOut:
    try:
        await econ_svc.spend_tokens(session, profile_id, body.amount)
    except econ_svc.EconomyNotFound:
        raise _econ_404(profile_id)
    except econ_svc.InsufficientTokens as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    await session.commit()
    return await standing(profile_id, session)


@router.post(
    "/{profile_id}/denial-timer",
    response_model=DenialTimerOut,
    status_code=status.HTTP_201_CREATED,
)
async def set_denial_timer(
    profile_id: uuid.UUID, body: DenialTimerIn, session: AsyncSession = Depends(get_session)
) -> DenialTimerOut:
    timer = await econ_svc.set_denial_timer(
        session, profile_id, reason=body.reason, ends_at=body.ends_at
    )
    await session.commit()
    return DenialTimerOut.model_validate(timer)


@router.post("/{profile_id}/denial-timer/clear")
async def clear_denial_timers(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    cleared = await econ_svc.clear_denial_timers(session, profile_id)
    await session.commit()
    return {"cleared": cleared}
