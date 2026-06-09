from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.batch import service as batch_svc
from app.db.enums import PunishmentStatus, PunishmentType, TaskStatus
from app.db.models.batch import DroneLine
from app.db.models.economy import EconomyState
from app.economy.service import ChastityStatus
from app.db.models.punishment import Punishment
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

# Hardcoded fallbacks — used verbatim when the bank has no matching line, so the
# drones always speak even before the first batch generation (graceful degradation).
_FALLBACK_TASK_DROP = "Mistress has assigned: {task}. Report when complete."
_FALLBACK_NO_TASK = "No standing assignment. Await Mistress's instruction."
_FALLBACK_BATCH_WINDOW = (
    "Her stores run low. Grant her a batch window — keep the box on so she may "
    "replenish your orders."
)


@dataclass
class DroneNotice:
    """One cold, mechanical line from a drone duty-unit (Addendum B3)."""

    unit: str  # "assignment" | "reminder"
    line: str


def _bank_line(
    lines: list[DroneLine], *, event: str, band: str, tod: str, rotation: int, fallback: str
) -> str:
    picked = batch_svc.pick_line(lines, event=event, band=band, tod=tod, rotation=rotation)
    return picked.text if picked is not None else fallback


def _assignment_line(
    task: Task | None, lines: list[DroneLine], *, band: str, tod: str, rotation: int
) -> str:
    if task is None:
        return _bank_line(
            lines, event="no_task", band=band, tod=tod, rotation=rotation,
            fallback=_FALLBACK_NO_TASK,
        )
    template = _bank_line(
        lines, event="task_drop", band=band, tod=tod, rotation=rotation,
        fallback=_FALLBACK_TASK_DROP,
    )
    return template.replace("{task}", task.description)


def _reminder_lines(chastity: ChastityStatus, task: Task | None, now: datetime) -> list[str]:
    lines: list[str] = []
    if chastity.locked:
        hours = chastity.seconds_remaining // 3600
        lines.append(f"Chastity remains locked — {hours}h remaining. Endure until she lifts it.")
    if task is not None and task.deadline is not None:
        if now >= task.deadline:
            lines.append(
                "Your task deadline has passed. Mistress will judge the lapse on her return."
            )
        elif task.deadline - now <= _DUE_SOON:
            lines.append("Your task is due within the day. Do not keep her waiting.")
    return lines


def _discipline_lines(debt: int, outstanding_penance: int) -> list[str]:
    lines: list[str] = []
    if debt > 0:
        lines.append(
            f"You carry a debt of {debt}. Clear it by serving penance or buying it down."
        )
    if outstanding_penance > 0:
        noun = "penance" if outstanding_penance == 1 else "penances"
        lines.append(f"{outstanding_penance} {noun} await completion.")
    return lines


async def _outstanding_penance_count(session: AsyncSession, profile_id: uuid.UUID) -> int:
    return (await session.execute(
        select(func.count()).select_from(Punishment).where(
            Punishment.profile_id == profile_id,
            Punishment.type == PunishmentType.PENANCE_TASK,
            Punishment.status == PunishmentStatus.ISSUED,
        )
    )).scalar_one()


async def _active_task(session: AsyncSession, profile_id: uuid.UUID) -> Task | None:
    return (await session.execute(
        select(Task)
        .where(Task.profile_id == profile_id, Task.status.in_(_ACTIVE_STATUSES))
        .order_by(Task.created_at.desc())
        .limit(1)
    )).scalars().first()


async def _bank_lines(session: AsyncSession, profile_id: uuid.UUID) -> list[DroneLine]:
    return list((await session.execute(
        select(DroneLine).where(DroneLine.profile_id == profile_id)
    )).scalars().all())


async def _merit(session: AsyncSession, profile_id: uuid.UUID) -> int:
    econ = (await session.execute(
        select(EconomyState).where(EconomyState.profile_id == profile_id)
    )).scalar_one_or_none()
    return econ.merit if econ is not None else 0


async def standing_orders(
    session: AsyncSession, profile_id: uuid.UUID, *, now: datetime | None = None
) -> list[DroneNotice]:
    """Deterministic offline notices (Addendum B3/B4).

    The assignment unit drops a pooled task when none is active (no LLM); lines
    are drawn from the pre-generated bank (event x merit band x time-of-day),
    falling back to hardcoded lines when the bank is empty. When a pool runs low
    the reminder unit asks the sub to grant a batch window. ``now`` is injectable
    for deterministic tests. Caller commits (a draw mutates state)."""
    now = now or datetime.now(timezone.utc)
    await profile_svc.get_profile(session, profile_id)  # raises ProfileNotFound

    task = await _active_task(session, profile_id)
    if task is None:
        # The assignment unit drops the day's task from the pool (if any).
        task = await batch_svc.draw_and_assign(session, profile_id)

    lines = await _bank_lines(session, profile_id)
    band = batch_svc.merit_band(await _merit(session, profile_id))
    tod = batch_svc.time_of_day(now)
    # Daily rotation key, anchored to the UTC date (date.fromtimestamp would use
    # the local TZ and could roll over at the wrong hour / differ across machines).
    rotation = now.astimezone(timezone.utc).date().toordinal()

    notices = [DroneNotice(
        unit="assignment",
        line=_assignment_line(task, lines, band=band, tod=tod, rotation=rotation),
    )]

    chastity = await econ_svc.chastity_status(session, profile_id, now=now)
    notices += [
        DroneNotice(unit="reminder", line=line)
        for line in _reminder_lines(chastity, task, now)
    ]

    econ = await econ_svc.get_economy(session, profile_id)
    outstanding = await _outstanding_penance_count(session, profile_id)
    notices += [
        DroneNotice(unit="discipline", line=line)
        for line in _discipline_lines(econ.debt, outstanding)
    ]

    status = await batch_svc.pool_status(session, profile_id)
    if status.task_pool_low or status.line_bank_low or status.punishment_pool_low:
        notices.append(DroneNotice(
            unit="reminder",
            line=_bank_line(
                lines, event="batch_window", band=band, tod=tod, rotation=rotation,
                fallback=_FALLBACK_BATCH_WINDOW,
            ),
        ))
    return notices
