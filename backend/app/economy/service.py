from __future__ import annotations

import math
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import TaskStatus
from app.db.models.economy import DenialTimer, EconomyState
from app.db.models.task import Task

# Merit bounds — identical to app.persona.disposition (the disposition reads this merit).
MERIT_MIN, MERIT_MAX = -100, 100

# Rank ladder by current merit (descending thresholds). Tunable; "sustained merit"
# smoothing is a future refinement.
_RANK_TIERS: tuple[tuple[int, str], ...] = (
    (80, "paragon"),
    (50, "adept"),
    (20, "disciplined"),
    (-20, "novice"),
)
_LOWEST_RANK = "remedial"

# Streak multiplier on consecutive passes (rewards sustained obedience; tunable).
STREAK_STEP = 0.25
STREAK_MAX_MULT = 2.0


class EconomyNotFound(Exception):
    pass


class InsufficientTokens(Exception):
    pass


def rank_for(merit: int) -> str:
    for threshold, name in _RANK_TIERS:
        if merit >= threshold:
            return name
    return _LOWEST_RANK


def _clamp_merit(value: int) -> int:
    return max(MERIT_MIN, min(MERIT_MAX, value))


async def get_economy(session: AsyncSession, profile_id: uuid.UUID) -> EconomyState:
    econ = (await session.execute(
        select(EconomyState).where(EconomyState.profile_id == profile_id)
    )).scalar_one_or_none()
    if econ is None:
        raise EconomyNotFound(str(profile_id))
    return econ


async def adjust_merit(
    session: AsyncSession, profile_id: uuid.UUID, delta: int
) -> EconomyState:
    """Apply a bounded merit change and recompute rank (atomic; caller commits)."""
    econ = await get_economy(session, profile_id)
    econ.merit = _clamp_merit(econ.merit + delta)
    econ.rank = rank_for(econ.merit)
    await session.flush()
    return econ


async def grant_tokens(
    session: AsyncSession, profile_id: uuid.UUID, amount: int
) -> EconomyState:
    """Grant earned tokens (amount must be >= 0; caller commits)."""
    if amount < 0:
        raise ValueError("grant amount must be non-negative")
    econ = await get_economy(session, profile_id)
    econ.tokens += amount
    await session.flush()
    return econ


async def spend_tokens(
    session: AsyncSession, profile_id: uuid.UUID, amount: int
) -> EconomyState:
    """Spend tokens; never goes negative (raises InsufficientTokens). Caller commits."""
    if amount < 0:
        raise ValueError("spend amount must be non-negative")
    econ = await get_economy(session, profile_id)
    if econ.tokens < amount:
        raise InsufficientTokens(f"have {econ.tokens}, need {amount}")
    econ.tokens -= amount
    await session.flush()
    return econ


async def set_denial_timer(
    session: AsyncSession, profile_id: uuid.UUID, *, reason: str, ends_at: datetime
) -> DenialTimer:
    timer = DenialTimer(profile_id=profile_id, reason=reason, ends_at=ends_at, active=True)
    session.add(timer)
    await session.flush()
    return timer


async def active_denial_timers(
    session: AsyncSession, profile_id: uuid.UUID
) -> list[DenialTimer]:
    rows = (await session.execute(
        select(DenialTimer)
        .where(DenialTimer.profile_id == profile_id, DenialTimer.active.is_(True))
        .order_by(DenialTimer.created_at)
    )).scalars().all()
    return list(rows)


async def clear_denial_timers(session: AsyncSession, profile_id: uuid.UUID) -> int:
    timers = await active_denial_timers(session, profile_id)
    for timer in timers:
        timer.active = False
    await session.flush()
    return len(timers)


def _streak_multiplier(consecutive_passes: int) -> float:
    """1.0 for a lone pass, growing by STREAK_STEP per consecutive pass, capped."""
    steps = max(consecutive_passes - 1, 0)
    return min(1.0 + STREAK_STEP * steps, STREAK_MAX_MULT)


async def _recent_pass_streak(session: AsyncSession, profile_id: uuid.UUID) -> int:
    """Count the most-recent run of consecutive VERIFIED_PASS tasks (newest first)."""
    statuses = (await session.execute(
        select(Task.status)
        .where(
            Task.profile_id == profile_id,
            Task.status.in_(
                (TaskStatus.VERIFIED_PASS, TaskStatus.VERIFIED_FAIL, TaskStatus.MISSED)
            ),
        )
        .order_by(Task.updated_at.desc())
    )).scalars().all()
    streak = 0
    for status in statuses:
        if status is TaskStatus.VERIFIED_PASS:
            streak += 1
        else:
            break
    return streak


async def apply_task_outcome(session: AsyncSession, task: Task) -> EconomyState:
    """Apply a terminal task's merit stakes to the economy (spec 6 React -> spec 7).

    pass -> +merit_reward * streak_multiplier; fail -> -merit_fail_penalty;
    miss -> -merit_miss_penalty. Non-terminal statuses are a no-op. Caller commits.
    """
    if task.status is TaskStatus.VERIFIED_PASS:
        streak = await _recent_pass_streak(session, task.profile_id)
        # Half-up rounding (math.floor(x + 0.5)) for deterministic streak rewards;
        # Python's round() uses banker's rounding (round(12.5) == 12).
        delta = math.floor(task.merit_reward * _streak_multiplier(streak) + 0.5)
    elif task.status is TaskStatus.VERIFIED_FAIL:
        delta = -task.merit_fail_penalty
    elif task.status is TaskStatus.MISSED:
        delta = -task.merit_miss_penalty
    else:
        return await get_economy(session, task.profile_id)  # non-terminal -> no change
    return await adjust_merit(session, task.profile_id, delta)
