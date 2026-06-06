from __future__ import annotations

# Built-in kink-sheet vocabulary for v1. The user rates each (favorite/like/
# curious/soft_limit/hard_limit/na); custom kinks may be added later.
KINK_CATALOG: tuple[str, ...] = (
    "bondage",
    "spanking",
    "impact_play",
    "orgasm_control",
    "chastity",
    "service",
    "humiliation",
    "exhibitionism",
    "sensory_deprivation",
    "roleplay",
    "discipline",
    "edging",
    "worship",
    "tasks_and_chores",
)

_KNOWN = frozenset(KINK_CATALOG)


def is_known_kink(name: str) -> bool:
    return name in _KNOWN
