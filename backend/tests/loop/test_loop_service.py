import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import Settings
from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.loop import Proof, TaskTimer
from app.db.models.memory import MemoryEpisode
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
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


async def test_submit_proof_records_proof_and_proof_submitted(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="tidy desk", proof_requirement=ProofRequirement.HONOR,
    )
    await session.commit()
    await loop_svc.start_task(session, task.id)
    await session.commit()
    proof = await loop_svc.submit_proof(session, task.id, report="Cleared and wiped it.")
    await session.commit()

    assert proof.content == "Cleared and wiped it."
    refreshed = await session.get(type(task), task.id)
    assert refreshed.status is TaskStatus.PROOF_SUBMITTED


async def test_verify_task_honor_pass_sets_verified_pass(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="tidy desk", proof_requirement=ProofRequirement.HONOR,
    )
    await session.commit()
    await loop_svc.submit_proof(session, task.id, report="Cleared, wiped, and organized the cables.")
    await session.commit()

    provider = MockLLMProvider(scripted=[ChatResult(
        content='{"verdict": "pass", "confidence": 90, "reasoning": "detailed", "issues": []}'
    )])
    verified = await loop_svc.verify_task(session, task.id, provider, Settings())
    await session.commit()

    assert verified.status is TaskStatus.VERIFIED_PASS
    pr = (await session.execute(select(Proof).where(Proof.task_id == task.id))).scalar_one()
    assert pr.verdict == "pass"
    assert pr.confidence == 90


async def test_verify_task_honor_fail_sets_verified_fail(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="tidy desk", proof_requirement=ProofRequirement.HONOR,
    )
    await session.commit()
    await loop_svc.submit_proof(session, task.id, report="meh")
    await session.commit()

    provider = MockLLMProvider(scripted=[ChatResult(
        content='{"verdict": "fail", "confidence": 20, "reasoning": "no detail", "issues": ["vague"]}'
    )])
    verified = await loop_svc.verify_task(session, task.id, provider, Settings())
    await session.commit()
    assert verified.status is TaskStatus.VERIFIED_FAIL


async def test_verify_timer_task_passes_on_sufficient_elapsed(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="meditate", proof_requirement=ProofRequirement.TIMER,
        required_seconds=1,
    )
    await session.commit()
    await loop_svc.start_task(session, task.id)
    await session.commit()
    # backdate the timer start so elapsed >= required without sleeping
    tt = (await session.execute(select(TaskTimer).where(TaskTimer.task_id == task.id))).scalar_one()
    tt.started_at = tt.started_at - timedelta(seconds=10)
    await session.commit()
    await loop_svc.submit_proof(session, task.id)  # stops the timer
    await session.commit()

    verified = await loop_svc.verify_task(session, task.id, MockLLMProvider(), Settings())
    await session.commit()
    assert verified.status is TaskStatus.VERIFIED_PASS
