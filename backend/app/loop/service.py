from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.loop import Proof, TaskTimer
from app.db.models.task import Task
from app.llm.provider import LLMProvider
from app.loop import verification
from app.memory import service as mem_svc
from app.services import profile as profile_svc


class TaskNotFound(Exception):
    pass


async def _get_task(session: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise TaskNotFound(str(task_id))
    return task


async def assign_task(
    session: AsyncSession,
    profile_id: uuid.UUID,
    *,
    description: str,
    proof_requirement: ProofRequirement,
    deadline: datetime | None = None,
    merit_reward: int = 0,
    merit_fail_penalty: int = 0,
    merit_miss_penalty: int = 0,
    required_seconds: int | None = None,
) -> Task:
    await profile_svc.get_profile(session, profile_id)  # 404 guard
    task = Task(
        profile_id=profile_id,
        description=description,
        proof_requirement=proof_requirement,
        deadline=deadline,
        merit_reward=merit_reward,
        merit_fail_penalty=merit_fail_penalty,
        merit_miss_penalty=merit_miss_penalty,
        status=TaskStatus.ASSIGNED,
    )
    session.add(task)
    await session.flush()
    if proof_requirement is ProofRequirement.TIMER:
        session.add(TaskTimer(task_id=task.id, required_seconds=required_seconds or 0))
    await mem_svc.enqueue_episode(
        session,
        profile_id,
        name="task assigned",
        body=f"Assigned task: {description} (proof: {proof_requirement.value}).",
        source="text",
        source_description="task",
        reference_time=datetime.now(timezone.utc),
    )
    await session.flush()
    return task


async def start_task(session: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await _get_task(session, task_id)
    task.status = TaskStatus.IN_PROGRESS
    if task.proof_requirement is ProofRequirement.TIMER:
        timer = (await session.execute(
            select(TaskTimer).where(TaskTimer.task_id == task.id)
        )).scalar_one_or_none()
        if timer is not None and timer.started_at is None:
            timer.started_at = datetime.now(timezone.utc)
    await session.flush()
    return task


async def submit_proof(
    session: AsyncSession, task_id: uuid.UUID, *, report: str = ""
) -> Proof:
    task = await _get_task(session, task_id)
    if task.proof_requirement is ProofRequirement.TIMER:
        timer = (await session.execute(
            select(TaskTimer).where(TaskTimer.task_id == task.id)
        )).scalar_one_or_none()
        if timer is not None and timer.stopped_at is None:
            timer.stopped_at = datetime.now(timezone.utc)
    proof = Proof(task_id=task.id, profile_id=task.profile_id, content=report)
    session.add(proof)
    task.status = TaskStatus.PROOF_SUBMITTED
    await session.flush()
    return proof


async def verify_task(
    session: AsyncSession, task_id: uuid.UUID, provider: LLMProvider, settings: Settings
) -> Task:
    task = await _get_task(session, task_id)
    task.status = TaskStatus.VERIFYING

    proof = (await session.execute(
        select(Proof).where(Proof.task_id == task.id).order_by(Proof.created_at.desc())
    )).scalars().first()
    timer = (await session.execute(
        select(TaskTimer).where(TaskTimer.task_id == task.id)
    )).scalar_one_or_none()

    result = await verification.verify(
        task,
        report=proof.content if proof is not None else "",
        timer=timer,
        provider=provider,
        settings=settings,
    )

    if proof is not None:
        proof.verdict = result.verdict
        proof.confidence = result.confidence
        proof.reasoning = result.reasoning
        proof.issues = result.issues

    if result.verdict == verification.PASS:
        task.status = TaskStatus.VERIFIED_PASS
    elif result.verdict == verification.FAIL:
        task.status = TaskStatus.VERIFIED_FAIL
    else:
        task.status = TaskStatus.PROOF_SUBMITTED  # re_proof/pending -> awaiting another attempt

    # TODO(M7): apply the task's merit stakes (reward/fail penalty) via the economy service.
    await mem_svc.enqueue_episode(
        session,
        task.profile_id,
        name="task verified",
        body=(
            f"Task '{task.description}' verification: {result.verdict} "
            f"(confidence {result.confidence}). {result.reasoning}"
        ),
        source="text",
        source_description="task",
        reference_time=datetime.now(timezone.utc),
    )
    await session.flush()
    return task
