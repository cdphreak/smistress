from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.enums import ProofRequirement, PunishmentType, TaskStatus
from app.db.models.loop import Proof, TaskTimer
from app.db.models.task import Task
from app.discipline import service as disc_svc
from app.economy import service as econ_svc
from app.llm.provider import LLMProvider
from app.loop import verification
from app.memory import service as mem_svc
from app.safety import service as safety_svc
from app.services import profile as profile_svc


class TaskNotFound(Exception):
    pass


class TaskNotVerifiable(Exception):
    pass


async def _get_task(session: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise TaskNotFound(str(task_id))
    return task


# Default automatic consequence for a miss/fail until the generated punishment
# pool + deterministic selection lands (M4b). Severity scales with the offence.
_AUTO_PUNISHMENT_TYPE = PunishmentType.CHASTITY_EXTENSION


async def apply_terminal_discipline(session: AsyncSession, task: Task) -> None:
    """At a terminal task status, run the discipline unit (Addendum B7):
    PASS settles a linked penance; FAIL/MISS issues a punishment (debt accrues)."""
    if task.status is TaskStatus.VERIFIED_PASS:
        await disc_svc.settle_penance(session, task)
    elif task.status in (TaskStatus.VERIFIED_FAIL, TaskStatus.MISSED):
        severity = 2 if task.status is TaskStatus.VERIFIED_FAIL else 1
        await disc_svc.issue_punishment(
            session, task.profile_id, type=_AUTO_PUNISHMENT_TYPE, severity=severity,
            reason=f"{task.status.value}: {task.description}",
        )
    await session.flush()


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


# Statuses that can still lapse into "missed" (no proof submitted yet).
_LAPSABLE = (TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS)

# Terminal statuses — re-verifying these is rejected (idempotency guard).
_TERMINAL = (TaskStatus.VERIFIED_PASS, TaskStatus.VERIFIED_FAIL, TaskStatus.MISSED)


async def sweep_missed(session: AsyncSession, profile_id: uuid.UUID | None = None) -> int:
    """Mark overdue, un-submitted tasks as missed (deadline passed with no proof; spec 6).

    Tasks already in proof_submitted/verifying are awaiting verification, not missed.
    """
    now = datetime.now(timezone.utc)
    stmt = select(Task).where(
        Task.deadline.is_not(None),
        Task.deadline < now,
        Task.status.in_(_LAPSABLE),
    )
    if profile_id is not None:
        stmt = stmt.where(Task.profile_id == profile_id)
    overdue = (await session.execute(stmt)).scalars().all()
    missed = 0
    for task in overdue:
        if await safety_svc.is_frozen(session, task.profile_id):
            continue  # halted by safeword or on hiatus -> no miss, no penalty (spec 9)
        task.status = TaskStatus.MISSED
        await session.flush()  # ensure status is set before applying the outcome
        await econ_svc.apply_task_outcome(session, task)
        await apply_terminal_discipline(session, task)
        await mem_svc.enqueue_episode(
            session,
            task.profile_id,
            name="task missed",
            body=f"Task '{task.description}' was missed (deadline passed with no proof).",
            source="text",
            source_description="task",
            reference_time=now,
        )
        missed += 1
    await session.flush()
    return missed


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
    if task.status in _TERMINAL:
        raise TaskNotVerifiable(f"task {task_id} is already {task.status.value}")
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

    if task.status in (TaskStatus.VERIFIED_PASS, TaskStatus.VERIFIED_FAIL):
        await econ_svc.apply_task_outcome(session, task)
        await apply_terminal_discipline(session, task)
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
