from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability import service as avail_svc
from app.db.session import get_session
from app.schemas.availability import AvailabilityOut, HeartbeatIn

router = APIRouter(prefix="/llm", tags=["availability"])


def _out(snap: avail_svc.AvailabilitySnapshot) -> AvailabilityOut:
    return AvailabilityOut(
        state=snap.state, online=snap.online, last_heartbeat_at=snap.last_heartbeat_at
    )


@router.post("/heartbeat", response_model=AvailabilityOut)
async def heartbeat(
    body: HeartbeatIn, session: AsyncSession = Depends(get_session)
) -> AvailabilityOut:
    await avail_svc.record_heartbeat(session, source=body.source)
    await session.commit()
    return _out(await avail_svc.snapshot(session))


@router.get("/availability", response_model=AvailabilityOut)
async def availability(session: AsyncSession = Depends(get_session)) -> AvailabilityOut:
    return _out(await avail_svc.snapshot(session))
