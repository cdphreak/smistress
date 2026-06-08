from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import TaskStatus
from app.db.models.economy import DenialTimer
from app.db.models.task import Task
from app.economy import service as econ_svc
from app.services import profile as profile_svc

# Task statuses that count as a live, outstanding assignment (mirrors app.chat.service).
_ACTIVE_STATUSES = (
    TaskStatus.ASSIGNED,
    TaskStatus.IN_PROGRESS,
    TaskStatus.PROOF_SUBMITTED,
    TaskStatus.VERIFYING,
)

# A task deadline within this window earns a "due soon" reminder.
_DUE_SOON = timedelta(hours=24)


@dataclass
class DroneNotice:
    """One cold, mechanical line from a drone duty-unit (Addendum B3)."""

    unit: str  # "assignment" | "reminder"
    line: str


def _assignment_line(task: Task | None) -> str:
    if task is None:
        return "No standing assignment. Await Mistress's instruction."
    return f"Mistress has assigned: {task.description}. Report when complete."


def _reminder_lines(
    timers: list[DenialTimer], task: Task | None, now: datetime
) -> list[str]:
    lines: list[str] = []
    for timer in timers:
        reason = f": {timer.reason}" if timer.reason else ""
        lines.append(f"Denial remains in effect{reason}. Endure it until she lifts it.")
    if task is not None and task.deadline is not None:
        if now >= task.deadline:
            lines.append(
                "Your task deadline has passed. Mistress will judge the lapse on her return."
            )
        elif task.deadline - now <= _DUE_SOON:
            lines.append("Your task is due within the day. Do not keep her waiting.")
    return lines


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
    timers = await econ_svc.active_denial_timers(session, profile_id)
    notices = [DroneNotice(unit="assignment", line=_assignment_line(task))]
    notices += [
        DroneNotice(unit="reminder", line=line)
        for line in _reminder_lines(timers, task, now)
    ]
    return notices
