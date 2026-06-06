from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models.loop import Proof
from app.db.models.task import Task
from app.db.session import get_session
from app.llm.factory import build_provider
from app.llm.provider import LLMProvider
from app.loop import service as loop_svc
from app.schemas.task import ProofIn, TaskCreate, TaskOut, VerdictOut
from app.services import profile as profile_svc

router = APIRouter(tags=["tasks"])
_settings = Settings()


def get_task_provider() -> LLMProvider:
    return build_provider(_settings)


def _task_404(task_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"task {task_id} not found"
    )


@router.post(
    "/profile/{profile_id}/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
)
async def assign(
    profile_id: uuid.UUID, body: TaskCreate, session: AsyncSession = Depends(get_session)
) -> TaskOut:
    try:
        task = await loop_svc.assign_task(
            session, profile_id,
            description=body.description, proof_requirement=body.proof_requirement,
            deadline=body.deadline, merit_reward=body.merit_reward,
            merit_fail_penalty=body.merit_fail_penalty, merit_miss_penalty=body.merit_miss_penalty,
            required_seconds=body.required_seconds,
        )
    except profile_svc.ProfileNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
    await session.commit()
    return TaskOut.model_validate(task)


@router.get("/profile/{profile_id}/tasks", response_model=list[TaskOut])
async def list_tasks(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[TaskOut]:
    rows = (await session.execute(
        select(Task).where(Task.profile_id == profile_id).order_by(Task.created_at)
    )).scalars().all()
    return [TaskOut.model_validate(t) for t in rows]


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> TaskOut:
    task = await session.get(Task, task_id)
    if task is None:
        raise _task_404(task_id)
    return TaskOut.model_validate(task)


@router.post("/tasks/{task_id}/start", response_model=TaskOut)
async def start(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> TaskOut:
    try:
        task = await loop_svc.start_task(session, task_id)
    except loop_svc.TaskNotFound:
        raise _task_404(task_id)
    await session.commit()
    return TaskOut.model_validate(task)


@router.post("/tasks/{task_id}/proof", response_model=TaskOut)
async def submit_proof(
    task_id: uuid.UUID, body: ProofIn, session: AsyncSession = Depends(get_session)
) -> TaskOut:
    try:
        await loop_svc.submit_proof(session, task_id, report=body.report)
        task = await session.get(Task, task_id)
    except loop_svc.TaskNotFound:
        raise _task_404(task_id)
    await session.commit()
    return TaskOut.model_validate(task)


@router.post("/tasks/{task_id}/verify", response_model=VerdictOut)
async def verify(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    provider: LLMProvider = Depends(get_task_provider),
) -> VerdictOut:
    try:
        task = await loop_svc.verify_task(session, task_id, provider, _settings)
    except loop_svc.TaskNotFound:
        raise _task_404(task_id)
    await session.commit()
    proof = (await session.execute(
        select(Proof).where(Proof.task_id == task_id).order_by(Proof.created_at.desc())
    )).scalars().first()
    return VerdictOut(
        task_id=task_id,
        status=task.status,
        verdict=proof.verdict if proof else None,
        confidence=proof.confidence if proof else None,
        reasoning=proof.reasoning if proof else "",
    )


@router.post("/profile/{profile_id}/tasks/sweep-missed")
async def sweep(
    profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    missed = await loop_svc.sweep_missed(session, profile_id)
    await session.commit()
    return {"missed": missed}
