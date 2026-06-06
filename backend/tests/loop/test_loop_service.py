import uuid

import pytest
from sqlalchemy import select

from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.loop import TaskTimer
from app.db.models.memory import MemoryEpisode
from app.loop import service as loop_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_assign_task_creates_assigned_and_seeds_episode(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="make the bed", proof_requirement=ProofRequirement.HONOR,
        merit_reward=5, merit_miss_penalty=8,
    )
    await session.commit()

    assert task.status is TaskStatus.ASSIGNED
    assert task.merit_reward == 5
    ep = (await session.execute(select(MemoryEpisode))).scalars().all()
    assert any("make the bed" in e.body for e in ep)


async def test_assign_timer_task_creates_timer(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="meditate", proof_requirement=ProofRequirement.TIMER,
        required_seconds=600,
    )
    await session.commit()
    tt = (await session.execute(select(TaskTimer).where(TaskTimer.task_id == task.id))).scalar_one()
    assert tt.required_seconds == 600
    assert tt.started_at is None


async def test_start_task_sets_in_progress_and_starts_timer(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="meditate", proof_requirement=ProofRequirement.TIMER,
        required_seconds=600,
    )
    await session.commit()
    started = await loop_svc.start_task(session, task.id)
    await session.commit()
    assert started.status is TaskStatus.IN_PROGRESS
    tt = (await session.execute(select(TaskTimer).where(TaskTimer.task_id == task.id))).scalar_one()
    assert tt.started_at is not None


async def test_start_unknown_task_raises(session):
    with pytest.raises(loop_svc.TaskNotFound):
        await loop_svc.start_task(session, uuid.uuid4())
