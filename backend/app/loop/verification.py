from __future__ import annotations

from dataclasses import dataclass, field

from app.config import Settings
from app.db.models.loop import TaskTimer

# Allowed verdicts (plain strings; persisted on Proof.verdict).
PASS = "pass"
FAIL = "fail"
RE_PROOF = "re_proof"
PENDING = "pending"


@dataclass
class VerdictResult:
    verdict: str  # pass | fail | re_proof | pending
    confidence: int | None  # 0-100, or None when not applicable
    reasoning: str
    issues: list[str] = field(default_factory=list)


def verify_none() -> VerdictResult:
    return VerdictResult(PASS, None, "no proof required", [])


def verify_timer(timer: TaskTimer) -> VerdictResult:
    if timer.started_at is None or timer.stopped_at is None:
        return VerdictResult(RE_PROOF, None, "timer was not started and stopped", ["timer not completed"])
    elapsed = (timer.stopped_at - timer.started_at).total_seconds()
    required = timer.required_seconds
    if elapsed >= required:
        return VerdictResult(PASS, 100, f"elapsed {elapsed:.0f}s >= required {required}s", [])
    return VerdictResult(
        FAIL, 100, f"elapsed {elapsed:.0f}s < required {required}s", ["insufficient duration"]
    )


def verify_media(settings: Settings) -> VerdictResult:
    # Configurable vision (spec 2): no vision model -> auto-pass (honor system for media).
    if not settings.vision_enabled:
        return VerdictResult(PASS, None, "no vision model configured — auto-passed", [])
    # Real image verification is M6b; until then a configured-vision media proof is pending.
    return VerdictResult(PENDING, None, "vision verification pending (M6b)", ["vision pending"])
