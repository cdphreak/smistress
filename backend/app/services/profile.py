from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.character import CharacterModel
from app.db.models.economy import DenialTimer, EconomyState
from app.db.models.loop import Proof, TaskTimer
from app.db.models.memory import MemoryEpisode
from app.db.models.message import Message
from app.db.models.safety import SafetyState
from app.db.models.task import Task
from app.db.models.profile import (
    ArchetypeResult,
    Goal,
    KinkEntry,
    SoContext,
    SubProfile,
    Toy,
)
from app.schemas.onboarding import (
    CharacterUpdate,
    GoalIn,
    KinkItem,
    PreferencesIn,
    ProfileCreate,
    SoContextIn,
    ToyIn,
)


class ProfileNotFound(Exception):
    pass


async def create_profile(session: AsyncSession, data: ProfileCreate) -> SubProfile:
    """Create the aggregate root plus its default character model and economy."""
    profile = SubProfile(
        intensity_ceiling=data.intensity_ceiling,
        aftercare_prefs=data.aftercare_prefs,
    )
    session.add(profile)
    await session.flush()  # populate profile.id
    session.add(CharacterModel(profile_id=profile.id))  # all-default persona
    session.add(EconomyState(profile_id=profile.id))
    session.add(SafetyState(profile_id=profile.id))
    await session.flush()
    return profile


async def delete_profile(session: AsyncSession, profile_id: uuid.UUID) -> None:
    """One-tap delete-everything (spec 9 data control). FK-safe order. Caller commits."""
    await get_profile(session, profile_id)  # raises ProfileNotFound

    # Children of `task` first (they FK to task.id).
    task_ids = (await session.execute(
        select(Task.id).where(Task.profile_id == profile_id)
    )).scalars().all()
    if task_ids:
        await session.execute(delete(Proof).where(Proof.task_id.in_(task_ids)))
        await session.execute(delete(TaskTimer).where(TaskTimer.task_id.in_(task_ids)))

    for model in (
        Message, Task, DenialTimer, EconomyState, CharacterModel, MemoryEpisode,
        SafetyState, KinkEntry, Toy, Goal, ArchetypeResult, SoContext,
    ):
        await session.execute(delete(model).where(model.profile_id == profile_id))

    await session.execute(delete(SubProfile).where(SubProfile.id == profile_id))
    await session.flush()


async def get_profile(session: AsyncSession, profile_id: uuid.UUID) -> SubProfile:
    profile = await session.get(SubProfile, profile_id)
    if profile is None:
        raise ProfileNotFound(str(profile_id))
    return profile


async def update_preferences(
    session: AsyncSession, profile_id: uuid.UUID, data: PreferencesIn
) -> SubProfile:
    profile = await get_profile(session, profile_id)  # raises ProfileNotFound
    profile.intensity_ceiling = data.intensity_ceiling
    profile.aftercare_prefs = data.aftercare_prefs
    await session.flush()
    return profile


async def get_character(session: AsyncSession, profile_id: uuid.UUID) -> CharacterModel:
    await get_profile(session, profile_id)  # 404 if profile missing
    char = (await session.execute(
        select(CharacterModel).where(CharacterModel.profile_id == profile_id)
    )).scalar_one()
    return char


async def latest_archetype_scores(
    session: AsyncSession, profile_id: uuid.UUID
) -> dict[str, int]:
    row = (await session.execute(
        select(ArchetypeResult)
        .where(ArchetypeResult.profile_id == profile_id)
        .order_by(ArchetypeResult.created_at.desc())
    )).scalars().first()
    return dict(row.scores) if row else {}


async def add_archetype_result(
    session: AsyncSession,
    profile_id: uuid.UUID,
    raw_answers: dict[str, int],
    scores: dict[str, int],
) -> ArchetypeResult:
    await get_profile(session, profile_id)
    result = ArchetypeResult(
        profile_id=profile_id, raw_answers=raw_answers, scores=scores
    )
    session.add(result)
    await session.flush()
    return result


async def replace_kinks(
    session: AsyncSession, profile_id: uuid.UUID, entries: list[KinkItem]
) -> None:
    """Full replace — the kink sheet is authoritative, not incremental."""
    await get_profile(session, profile_id)
    await session.execute(delete(KinkEntry).where(KinkEntry.profile_id == profile_id))
    for item in entries:
        session.add(
            KinkEntry(profile_id=profile_id, kink=item.kink, rating=item.rating)
        )
    await session.flush()


async def add_toy(session: AsyncSession, profile_id: uuid.UUID, data: ToyIn) -> Toy:
    await get_profile(session, profile_id)
    toy = Toy(
        profile_id=profile_id,
        name=data.name,
        type=data.type.value,  # store the plain enum value in the String column
        intiface_capable=data.intiface_capable,
        notes=data.notes,
    )
    session.add(toy)
    await session.flush()
    return toy


async def list_toys(session: AsyncSession, profile_id: uuid.UUID) -> list[Toy]:
    await get_profile(session, profile_id)
    return list((await session.execute(
        select(Toy).where(Toy.profile_id == profile_id).order_by(Toy.name)
    )).scalars().all())


async def add_goal(session: AsyncSession, profile_id: uuid.UUID, data: GoalIn) -> Goal:
    await get_profile(session, profile_id)
    goal = Goal(profile_id=profile_id, title=data.title, description=data.description)
    session.add(goal)
    await session.flush()
    return goal


async def list_goals(session: AsyncSession, profile_id: uuid.UUID) -> list[Goal]:
    await get_profile(session, profile_id)
    return list((await session.execute(
        select(Goal).where(Goal.profile_id == profile_id).order_by(Goal.created_at)
    )).scalars().all())


async def upsert_so_context(
    session: AsyncSession, profile_id: uuid.UUID, data: SoContextIn
) -> SoContext:
    await get_profile(session, profile_id)
    so = (await session.execute(
        select(SoContext).where(SoContext.profile_id == profile_id)
    )).scalar_one_or_none()
    if so is None:
        so = SoContext(profile_id=profile_id)
        session.add(so)
    so.description = data.description
    so.values = data.values
    so.dynamic = data.dynamic
    await session.flush()
    return so


async def update_character(
    session: AsyncSession, profile_id: uuid.UUID, data: CharacterUpdate
) -> CharacterModel:
    char = await get_character(session, profile_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(char, field, value)
    await session.flush()
    return char


async def get_profile_full(session: AsyncSession, profile_id: uuid.UUID) -> SubProfile:
    """Profile with child collections eagerly loaded (async-safe, no lazy IO)."""
    profile = (await session.execute(
        select(SubProfile)
        .where(SubProfile.id == profile_id)
        .options(
            selectinload(SubProfile.kinks),
            selectinload(SubProfile.toys),
            selectinload(SubProfile.goals),
            selectinload(SubProfile.so_context),
        )
    )).scalar_one_or_none()
    if profile is None:
        raise ProfileNotFound(str(profile_id))
    return profile
