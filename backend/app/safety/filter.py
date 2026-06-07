from __future__ import annotations

from collections.abc import Iterable

# Deterministic fallback when the model keeps crossing a hard limit after one
# corrective regeneration. Out-of-persona enough to be unmistakably safe.
SAFE_REPLY = (
    "I won't take us there — that crosses one of your hard limits. "
    "Let's redirect to something within bounds."
)


def _variants(term: str) -> tuple[str, ...]:
    t = term.strip().lower()
    return (t, t.replace("_", " ")) if "_" in t else (t,)


def scan_violations(text: str, hard_limits: Iterable[str]) -> list[str]:
    """Return the hard-limit terms that appear in `text` (case-insensitive).

    Underscore terms (e.g. 'breath_play') also match their spaced prose form.
    Order follows `hard_limits`; each term reported at most once.
    """
    hay = text.lower()
    hits: list[str] = []
    for term in hard_limits:
        if not term:
            continue
        if any(v in hay for v in _variants(term)) and term not in hits:
            hits.append(term)
    return hits


def corrective_note(violations: Iterable[str]) -> str:
    terms = ", ".join(violations)
    return (
        "Your previous reply referenced a hard limit "
        f"({terms}), which is NEVER permitted. Rewrite your reply so it does not "
        "mention, request, or imply that limit in any form. Stay in character otherwise."
    )
