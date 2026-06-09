from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db.enums import SupervisionMode
from app.db.models.profile import SubProfile
from app.services import profile as profile_svc


async def get_mode(session: AsyncSession, profile_id: uuid.UUID) -> SupervisionMode:
    profile = await profile_svc.get_profile(session, profile_id)  # raises ProfileNotFound
    return profile.supervision_mode


async def get_notes(session: AsyncSession, profile_id: uuid.UUID) -> dict[str, str]:
    profile = await profile_svc.get_profile(session, profile_id)
    return dict(profile.supervision_notes or {})


async def set_mode(
    session: AsyncSession, profile_id: uuid.UUID, mode: SupervisionMode
) -> SubProfile:
    """Set the supervision mode. Honored immediately (read every turn); no merit
    penalty — lowering control depth / entering vacation is a consent control
    (spec 9). Caller commits."""
    profile = await profile_svc.get_profile(session, profile_id)
    profile.supervision_mode = mode
    await session.flush()
    return profile


async def set_note(
    session: AsyncSession, profile_id: uuid.UUID, mode: SupervisionMode, note: str
) -> SubProfile:
    """Set the free-text 'what's possible right now' note for one mode. Caller commits."""
    profile = await profile_svc.get_profile(session, profile_id)
    notes = dict(profile.supervision_notes or {})
    notes[mode.value] = note
    profile.supervision_notes = notes
    flag_modified(profile, "supervision_notes")  # JSONB dict reassignment -> mark dirty
    await session.flush()
    return profile


async def economy_frozen(session: AsyncSession, profile_id: uuid.UUID) -> bool:
    """Vacation freezes the economy (Addendum B6): no task drops, no miss
    penalties, no debt accrual while active."""
    return (await get_mode(session, profile_id)) is SupervisionMode.VACATION
