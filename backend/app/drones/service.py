from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import TaskStatus
from app.db.models.task import Task
from app.services import profile as profile_svc

# Task statuses that count as a live, outstanding assignment (mirrors app.chat.service).
_ACTIVE_STATUSES = (
    TaskStatus.ASSIGNED,
    TaskStatus.IN_PROGRESS,
    TaskStatus.PROOF_SUBMITTED,
    TaskStatus.VERIFYING,
)


@dataclass
class DroneNotice:
    """One cold, mechanical line from a drone duty-unit (Addendum B3)."""

    unit: str  # "assignment" | "reminder"
    line: str


def _assignment_line(task: Task | None) -> str:
    if task is None:
        return "No standing assignment. Await Mistress's instruction."
    return f"Mistress has assigned: {task.description}. Report when complete."


async def _active_task(session: AsyncSession, profile_id: uuid.UUID) -> Task | None:
    return (await session.execute(
        select(Task)
        .where(Task.profile_id == profile_id, Task.status.in_(_ACTIVE_STATUSES))
        .order_by(Task.created_at.desc())
        .limit(1)
    )).scalars().first()


async def standing_orders(
    session: AsyncSession, profile_id: uuid.UUID, *, now: datetime | None = None
) -> list[DroneNotice]:
    """Deterministic offline notices from existing state (Addendum B3).

    No LLM and no content generation: the drones only surface what is already
    true. ``now`` is injectable for deterministic deadline tests.
    """
    now = now or datetime.now(timezone.utc)
    await profile_svc.get_profile(session, profile_id)  # raises ProfileNotFound
    task = await _active_task(session, profile_id)
    notices = [DroneNotice(unit="assignment", line=_assignment_line(task))]
    return notices
