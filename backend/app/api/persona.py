from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.persona import service as persona_svc
from app.schemas.persona import DispositionOut
from app.services import profile as profile_svc

router = APIRouter(prefix="/profile", tags=["persona"])


@router.get("/{profile_id}/disposition", response_model=DispositionOut)
async def get_disposition(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> DispositionOut:
    try:
        disp = await persona_svc.get_disposition(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"profile {profile_id} not found",
        )
    return DispositionOut(
        band=disp.band.value, standing=disp.standing, reason=disp.reason, line=disp.line
    )
