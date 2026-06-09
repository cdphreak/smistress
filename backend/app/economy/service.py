from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.enums import TaskStatus
from app.db.models.economy import ChastityTimer, EconomyState
from app.db.models.task import Task

_settings = Settings()

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


# ---------------------------------------------------------------------------
# Chastity timer
# ---------------------------------------------------------------------------


@dataclass
class ChastityStatus:
    locked: bool
    ends_at: datetime | None
    seconds_remaining: int


async def _get_or_create_chastity(
    session: AsyncSession, profile_id: uuid.UUID
) -> ChastityTimer:
    row = (await session.execute(
        select(ChastityTimer).where(ChastityTimer.profile_id == profile_id)
    )).scalar_one_or_none()
    if row is None:
        row = ChastityTimer(profile_id=profile_id)
        session.add(row)
        await session.flush()
    return row


async def chastity_status(
    session: AsyncSession, profile_id: uuid.UUID, *, now: datetime | None = None
) -> ChastityStatus:
    now = now or datetime.now(timezone.utc)
    row = (await session.execute(
        select(ChastityTimer).where(ChastityTimer.profile_id == profile_id)
    )).scalar_one_or_none()
    ends = row.ends_at if row else None
    if ends is not None and ends > now:
        return ChastityStatus(True, ends, int((ends - now).total_seconds()))
    return ChastityStatus(False, ends, 0)


async def set_chastity(
    session: AsyncSession, profile_id: uuid.UUID, *, ends_at: datetime, note: str = ""
) -> ChastityTimer:
    """Lock chastity until ``ends_at``. Caller commits."""
    row = await _get_or_create_chastity(session, profile_id)
    row.ends_at = ends_at
    if note:
        row.note = note
    await session.flush()
    return row


async def extend_chastity(
    session: AsyncSession, profile_id: uuid.UUID, *, hours: int, now: datetime | None = None
) -> ChastityTimer:
    """Push the chastity release out by ``hours`` (start from now if not locked).
    Only lengthens — never shortens. Caller commits."""
    now = now or datetime.now(timezone.utc)
    row = await _get_or_create_chastity(session, profile_id)
    base = row.ends_at if (row.ends_at is not None and row.ends_at > now) else now
    row.ends_at = base + timedelta(hours=hours)
    await session.flush()
    return row


async def set_chastity_note(
    session: AsyncSession, profile_id: uuid.UUID, note: str
) -> ChastityTimer:
    row = await _get_or_create_chastity(session, profile_id)
    row.note = note
    await session.flush()
    return row


async def lift_chastity(session: AsyncSession, profile_id: uuid.UUID) -> bool:
    """She releases the lock (ends_at -> None). Returns True if it was locked."""
    row = (await session.execute(
        select(ChastityTimer).where(ChastityTimer.profile_id == profile_id)
    )).scalar_one_or_none()
    was_locked = bool(row and row.ends_at is not None)
    if row is not None:
        row.ends_at = None
        await session.flush()
    return was_locked


# ---------------------------------------------------------------------------
# Debt ledger
# ---------------------------------------------------------------------------


async def adjust_debt(
    session: AsyncSession, profile_id: uuid.UUID, delta: int
) -> EconomyState:
    """Apply a debt change, clamped at zero (debt never negative). Caller commits."""
    econ = await get_economy(session, profile_id)
    econ.debt = max(0, econ.debt + delta)
    await session.flush()
    return econ


async def buy_down_debt(
    session: AsyncSession, profile_id: uuid.UUID, *, debt_points: int
) -> EconomyState:
    """Spend tokens to clear debt at a punishing rate (no merit). Clears as much as
    both the debt balance and the token purse allow. Caller commits."""
    if debt_points < 0:
        raise ValueError("debt_points must be non-negative")
    econ = await get_economy(session, profile_id)
    rate = _settings.buydown_tokens_per_debt
    affordable = econ.tokens // rate
    cleared = min(debt_points, econ.debt, affordable)
    econ.debt -= cleared
    econ.tokens -= cleared * rate
    await session.flush()
    return econ


# ---------------------------------------------------------------------------
# Task outcome application
# ---------------------------------------------------------------------------


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
