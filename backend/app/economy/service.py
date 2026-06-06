from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.economy import EconomyState

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
