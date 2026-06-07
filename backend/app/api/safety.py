from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.safety import service as safety_svc
from app.schemas.safety import (
    HiatusIn,
    LowerLimitIn,
    LowerLimitOut,
    SafetyStateOut,
    StopReceiptOut,
)
from app.services import profile as profile_svc

router = APIRouter(prefix="/profile", tags=["safety"])


def _not_found(profile_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"profile {profile_id} not found"
    )


async def _state_out(session: AsyncSession, profile_id: uuid.UUID) -> SafetyStateOut:
    state = await safety_svc.get_or_create_state(session, profile_id)
    return SafetyStateOut(
        is_halted=state.is_halted,
        on_hiatus=state.on_hiatus,
        consent_check_due=safety_svc.consent_check_due(state),
    )


@router.post("/{profile_id}/safeword", response_model=StopReceiptOut)
async def safeword(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> StopReceiptOut:
    try:
        receipt = await safety_svc.trigger_stop(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return StopReceiptOut(
        scene_halted=receipt.scene_halted,
        denial_lifted=receipt.denial_lifted,
        merit_penalty=receipt.merit_penalty,
        aftercare=receipt.aftercare,
        message=receipt.message,
    )


@router.post("/{profile_id}/resume", response_model=SafetyStateOut)
async def resume(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> SafetyStateOut:
    try:
        await safety_svc.resume(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return await _state_out(session, profile_id)


@router.get("/{profile_id}/safety", response_model=SafetyStateOut)
async def get_safety(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> SafetyStateOut:
    try:
        out = await _state_out(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()  # get_or_create may have inserted a row
    return out


@router.post("/{profile_id}/hiatus", response_model=SafetyStateOut)
async def set_hiatus(
    profile_id: uuid.UUID, body: HiatusIn, session: AsyncSession = Depends(get_session)
) -> SafetyStateOut:
    try:
        await safety_svc.set_hiatus(session, profile_id, body.on)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return await _state_out(session, profile_id)


@router.post("/{profile_id}/lower-limit", response_model=LowerLimitOut)
async def lower_limit(
    profile_id: uuid.UUID, body: LowerLimitIn, session: AsyncSession = Depends(get_session)
) -> LowerLimitOut:
    try:
        entry = await safety_svc.lower_limit(
            session, profile_id, kink=body.kink, rating=body.rating
        )
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    await session.commit()
    return LowerLimitOut(kink=entry.kink, rating=entry.rating)


@router.post("/{profile_id}/consent-check", response_model=SafetyStateOut)
async def consent_check(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> SafetyStateOut:
    try:
        await safety_svc.record_consent_check(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return await _state_out(session, profile_id)
