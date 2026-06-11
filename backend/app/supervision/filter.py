"""Deterministic, offline content filter (Addendum B6). Pure functions over
already-loaded objects — no DB, no session. The active supervision mode sets a
discreetness floor; tasks above the intensity ceiling are skipped (safety §9);
required toys must be discreet-capable when the mode demands discretion."""
from __future__ import annotations

from typing import Protocol

from app.db.enums import Discreetness, SupervisionMode

# Ordinal rank — higher is more discreet. A mode's floor admits anything at or
# above its rank.
_RANK: dict[Discreetness, int] = {
    Discreetness.OVERT: 0,
    Discreetness.DISCREET: 1,
    Discreetness.SILENT: 2,
}

_MODE_FLOOR: dict[SupervisionMode, Discreetness] = {
    SupervisionMode.FULL: Discreetness.OVERT,
    SupervisionMode.DISCREET: Discreetness.DISCREET,
    SupervisionMode.HOMEOFFICE: Discreetness.SILENT,
    SupervisionMode.TASK: Discreetness.OVERT,  # task mode constrains timing, not discretion
    SupervisionMode.VACATION: Discreetness.OVERT,  # never reached (gated upstream)
}


class _ToyLike(Protocol):
    discreet_capable: bool


def mode_min_discreetness(mode: SupervisionMode) -> Discreetness:
    return _MODE_FLOOR[mode]


def _meets_floor(discreetness: Discreetness, mode: SupervisionMode) -> bool:
    return _RANK[discreetness] >= _RANK[_MODE_FLOOR[mode]]


def _demands_discretion(mode: SupervisionMode) -> bool:
    """True when the mode requires required-toys to be discreet-capable."""
    return _RANK[_MODE_FLOOR[mode]] >= _RANK[Discreetness.DISCREET]


def _required_toys_ok(
    required_toy_ids: list[str], toys_by_id: dict[str, _ToyLike], mode: SupervisionMode
) -> bool:
    if not _demands_discretion(mode):
        return True
    for tid in required_toy_ids:
        toy = toys_by_id.get(str(tid))  # ids are JSONB-sourced; coerce to match str keys
        if toy is None or not toy.discreet_capable:
            return False
    return True


def task_allowed(
    mode: SupervisionMode,
    *,
    discreetness: Discreetness,
    intensity: int,
    required_toy_ids: list[str],
    toys_by_id: dict[str, _ToyLike],
    intensity_ceiling: int,
) -> bool:
    """Whether a pooled task may be dropped under the active mode. The intensity
    ceiling is a safety invariant applied in every mode (§9)."""
    if not _meets_floor(discreetness, mode):
        return False
    if intensity > intensity_ceiling:
        return False
    return _required_toys_ok(required_toy_ids, toys_by_id, mode)


def punishment_allowed(
    mode: SupervisionMode,
    *,
    discreetness: Discreetness,
    required_toy_ids: list[str],
    toys_by_id: dict[str, _ToyLike],
) -> bool:
    """Whether a pooled punishment may be drawn under the active mode (no intensity)."""
    if not _meets_floor(discreetness, mode):
        return False
    return _required_toys_ok(required_toy_ids, toys_by_id, mode)


_DIRECTIVES: dict[SupervisionMode, str] = {
    SupervisionMode.DISCREET: (
        "CONTENT FILTER: assign only discreet, quiet content; any required toy must be "
        "discreet-capable."
    ),
    SupervisionMode.HOMEOFFICE: (
        "CONTENT FILTER: she is in meetings — assign only silent, fully-covert content; "
        "expect no immediate reaction."
    ),
    SupervisionMode.TASK: (
        "CONTENT FILTER: assign only tasks with a graceful deadline; expect no immediate "
        "reaction."
    ),
}


def content_filter_directive(mode: SupervisionMode) -> str | None:
    """A one-line directive for the persona's authoritative-state block, or None
    when the mode imposes no content constraint (full/vacation)."""
    return _DIRECTIVES.get(mode)
