from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.economy import service as econ_svc
from app.schemas.economy import BuyDownIn, ChastityOut, SetChastityIn, StandingOut, TokenOp

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
    chastity = await econ_svc.chastity_status(session, profile_id)
    return StandingOut(
        merit=econ.merit, rank=econ.rank, tokens=econ.tokens, debt=econ.debt,
        chastity=ChastityOut(
            locked=chastity.locked, ends_at=chastity.ends_at,
            seconds_remaining=chastity.seconds_remaining,
        ),
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


@router.post("/{profile_id}/chastity", response_model=StandingOut)
async def set_chastity(
    profile_id: uuid.UUID, body: SetChastityIn, session: AsyncSession = Depends(get_session)
) -> StandingOut:
    await econ_svc.extend_chastity(session, profile_id, hours=body.hours)
    if body.note:
        await econ_svc.set_chastity_note(session, profile_id, body.note)
    await session.commit()
    return await standing(profile_id, session)


@router.post("/{profile_id}/chastity/lift", response_model=StandingOut)
async def lift_chastity(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> StandingOut:
    await econ_svc.lift_chastity(session, profile_id)
    await session.commit()
    return await standing(profile_id, session)


@router.post("/{profile_id}/debt/buy-down", response_model=StandingOut)
async def buy_down_debt(
    profile_id: uuid.UUID, body: BuyDownIn, session: AsyncSession = Depends(get_session)
) -> StandingOut:
    try:
        await econ_svc.buy_down_debt(session, profile_id, debt_points=body.debt_points)
    except econ_svc.EconomyNotFound:
        raise _econ_404(profile_id)
    await session.commit()
    return await standing(profile_id, session)
