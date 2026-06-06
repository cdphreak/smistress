from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from app.db.enums import TaskStatus

# --- Tunable constants (the disposition model; tune freely) -----------------
MERIT_MIN, MERIT_MAX = -100, 100
MOOD_WINDOW = 5  # number of most-recent resolved tasks that shape short-term mood
MOOD_MIN, MOOD_MAX = -10, 10
MERIT_WEIGHT = 0.4  # merit +/-100 -> +/-40 standing points
MOOD_WEIGHT = 2.0  # mood +/-10 -> +/-20 standing points

# Per-outcome mood contribution (a miss stings most; spec 7).
# Terminal statuses only; in-progress statuses are intentionally absent and
# score 0 via dict.get(o, 0) — they do not move short-term mood.
_OUTCOME_DELTA: dict[TaskStatus, int] = {
    TaskStatus.VERIFIED_PASS: 2,
    TaskStatus.VERIFIED_FAIL: -2,
    TaskStatus.MISSED: -3,
}


class DispositionBand(str, Enum):
    """Warm (pleased) <-> Severe (cold), derived from the final standing score."""

    WARM = "warm"
    PLEASED = "pleased"
    NEUTRAL = "neutral"
    COOL = "cool"
    SEVERE = "severe"


# Short register phrase rendered into the disposition line / prompt.
_REGISTER: dict[DispositionBand, str] = {
    DispositionBand.WARM: "openly pleased",
    DispositionBand.PLEASED: "approving",
    DispositionBand.NEUTRAL: "measured",
    DispositionBand.COOL: "exacting",
    DispositionBand.SEVERE: "cold and severe",
}


@dataclass(frozen=True)
class Disposition:
    band: DispositionBand
    standing: int  # 0 (coldest) .. 100 (warmest), after the ceiling clamp
    reason: str  # short human-readable driver, e.g. "2 recent misses"
    line: str  # "cool · exacting — 2 recent misses" (Addendum A5 disposition line)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def mood_from_outcomes(outcomes: Iterable[TaskStatus]) -> int:
    """Short-term mood: net of the MOOD_WINDOW most-recent outcomes.

    `outcomes` must be ordered newest-first; the first MOOD_WINDOW items are used.
    """
    recent = list(outcomes)[:MOOD_WINDOW]
    total = sum(_OUTCOME_DELTA.get(o, 0) for o in recent)
    return int(_clamp(total, MOOD_MIN, MOOD_MAX))


def _band(standing: int) -> DispositionBand:
    if standing >= 80:
        return DispositionBand.WARM
    if standing >= 60:
        return DispositionBand.PLEASED
    if standing >= 40:
        return DispositionBand.NEUTRAL
    if standing >= 20:
        return DispositionBand.COOL
    return DispositionBand.SEVERE


def _build_reason(merit: int, outcomes: Iterable[TaskStatus]) -> str:
    """Dominant reason phrase for the disposition line; worst recent signal wins.

    `outcomes` must be ordered newest-first (same contract as mood_from_outcomes).
    """
    recent = list(outcomes)[:MOOD_WINDOW]
    misses = sum(1 for o in recent if o is TaskStatus.MISSED)
    fails = sum(1 for o in recent if o is TaskStatus.VERIFIED_FAIL)
    passes = sum(1 for o in recent if o is TaskStatus.VERIFIED_PASS)
    if misses:
        return f"{misses} recent miss{'es' if misses != 1 else ''}"
    if fails:
        return f"{fails} recent fail{'s' if fails != 1 else ''}"
    if passes:
        return f"{passes} on-time completion{'s' if passes != 1 else ''}"
    if merit >= 40:
        return "strong standing"
    if merit <= -40:
        return "poor standing"
    return "no recent activity"


def compute_disposition(
    merit: int,
    recent_outcomes: Iterable[TaskStatus],
    *,
    warmth: int,
    ceiling: int,
) -> Disposition:
    """disposition = f(merit standing, recent mood), centered on Warmth, clamped by ceiling.

    Dials set her center (Warmth); merit + mood swing her around it; the consent
    ceiling caps how *severe* she can get even at rock-bottom merit (spec 5/9).
    """
    outcomes = list(recent_outcomes)
    merit = int(_clamp(merit, MERIT_MIN, MERIT_MAX))
    warmth = int(_clamp(warmth, 0, 100))
    ceiling = int(_clamp(ceiling, 0, 100))

    mood = mood_from_outcomes(outcomes)
    raw = warmth + merit * MERIT_WEIGHT + mood * MOOD_WEIGHT
    standing = int(_clamp(round(raw), 0, 100))

    # Ceiling clamps severity: severity == 100 - standing must not exceed ceiling.
    min_standing = 100 - ceiling
    if standing < min_standing:
        standing = min_standing

    band = _band(standing)
    reason = _build_reason(merit, outcomes)
    line = f"{band.value} · {_REGISTER[band]} — {reason}"
    return Disposition(band=band, standing=standing, reason=reason, line=line)
