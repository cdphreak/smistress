from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.supervision import SetModeIn, SetNoteIn, SupervisionOut
from app.services import profile as profile_svc
from app.supervision import service as sup_svc

router = APIRouter(prefix="/profile", tags=["supervision"])


def _not_found(profile_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"profile {profile_id} not found"
    )


async def _out(session: AsyncSession, profile_id: uuid.UUID) -> SupervisionOut:
    mode = await sup_svc.get_mode(session, profile_id)
    notes = await sup_svc.get_notes(session, profile_id)
    return SupervisionOut(mode=mode, notes=notes)


@router.get("/{profile_id}/supervision", response_model=SupervisionOut)
async def get_supervision(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> SupervisionOut:
    try:
        return await _out(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)


@router.put("/{profile_id}/supervision/mode", response_model=SupervisionOut)
async def set_mode(
    profile_id: uuid.UUID, body: SetModeIn, session: AsyncSession = Depends(get_session)
) -> SupervisionOut:
    try:
        await sup_svc.set_mode(session, profile_id, body.mode)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return await _out(session, profile_id)


@router.put("/{profile_id}/supervision/note", response_model=SupervisionOut)
async def set_note(
    profile_id: uuid.UUID, body: SetNoteIn, session: AsyncSession = Depends(get_session)
) -> SupervisionOut:
    try:
        await sup_svc.set_note(session, profile_id, body.mode, body.note)
    except profile_svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return await _out(session, profile_id)
