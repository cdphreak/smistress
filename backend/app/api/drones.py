from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.drones import service as drone_svc
from app.schemas.drones import DroneNoticeOut, StandingOrdersOut
from app.services import profile as profile_svc

router = APIRouter(prefix="/profile", tags=["drones"])


@router.get("/{profile_id}/standing-orders", response_model=StandingOrdersOut)
async def standing_orders(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> StandingOrdersOut:
    try:
        notices = await drone_svc.standing_orders(session, profile_id)
    except profile_svc.ProfileNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"profile {profile_id} not found"
        )
    return StandingOrdersOut(
        notices=[DroneNoticeOut(unit=n.unit, line=n.line) for n in notices]
    )
