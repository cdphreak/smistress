from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models.batch import DroneLine, TaskPoolItem

# Module-level Settings instance, matching the convention in availability/service.py.
_settings = Settings()

# --- Banding (tunable; mirrors the spirit of the disposition bands) ---------
_HIGH_MERIT = 50
_LOW_MERIT = 0


def merit_band(merit: int) -> str:
    if merit >= _HIGH_MERIT:
        return "high"
    if merit < _LOW_MERIT:
        return "low"
    return "mid"


def time_of_day(now: datetime) -> str:
    h = now.hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "day"
    if 17 <= h < 22:
        return "evening"
    return "night"


def _score(line: DroneLine, band: str, tod: str) -> int:
    """Specificity score for a candidate line; -1 means 'excluded' (wrong band/tod)."""
    score = 0
    if line.merit_band == band:
        score += 2
    elif line.merit_band == "any":
        score += 1
    else:
        return -1
    if line.time_of_day == tod:
        score += 2
    elif line.time_of_day == "any":
        score += 1
    else:
        return -1
    return score


def pick_line(
    lines: list[DroneLine], *, event: str, band: str, tod: str, rotation: int
) -> DroneLine | None:
    """Most-specific matching line for an event, rotated deterministically.

    ``rotation`` (e.g. the day ordinal) selects among equally-specific candidates
    so the line is stable within a render/day but varies day to day. Returns None
    when the bank has no usable line for the event (caller falls back to a
    hardcoded line so the drones always speak).
    """
    scored = [(line, _score(line, band, tod)) for line in lines if line.event == event]
    scored = [(line, s) for line, s in scored if s >= 0]
    if not scored:
        return None
    best = max(s for _, s in scored)
    top = sorted((line for line, s in scored if s == best), key=lambda line: str(line.id))
    return top[rotation % len(top)]


@dataclass
class PoolStatus:
    task_pool: int  # unconsumed task pool items
    line_bank: int  # total drone lines
    task_pool_low: bool
    line_bank_low: bool


async def pool_status(session: AsyncSession, profile_id: uuid.UUID) -> PoolStatus:
    tasks = (await session.execute(
        select(func.count())
        .select_from(TaskPoolItem)
        .where(TaskPoolItem.profile_id == profile_id, TaskPoolItem.consumed.is_(False))
    )).scalar_one()
    lines = (await session.execute(
        select(func.count()).select_from(DroneLine).where(DroneLine.profile_id == profile_id)
    )).scalar_one()
    return PoolStatus(
        task_pool=tasks,
        line_bank=lines,
        task_pool_low=tasks <= _settings.batch_task_low,
        line_bank_low=lines <= _settings.batch_line_low,
    )
