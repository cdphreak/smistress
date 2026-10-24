from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.config import Settings
from app.db.enums import ProofRequirement
from app.db.models.loop import TaskTimer
from app.db.models.task import Task
from app.llm.provider import LLMProvider
from app.llm.types import ChatMessage

# Allowed verdicts (plain strings; persisted on Proof.verdict).
PASS = "pass"
FAIL = "fail"
RE_PROOF = "re_proof"
PENDING = "pending"
PENDING_REVIEW = "pending_review"


@dataclass
class VerdictResult:
    verdict: str  # pass | fail | re_proof | pending | pending_review
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


_HONOR_SYSTEM = (
    "You are a strict, fair verifier of a completed real-world task. Judge ONLY whether the "
    "written report credibly demonstrates the task was completed as required. Be exacting: "
    "vague, evasive, or internally inconsistent reports fail or require re-proof. "
    'Respond with ONLY a JSON object: {"verdict": "pass"|"fail"|"re_proof", '
    '"confidence": <0-100 integer>, "reasoning": "<one sentence>", "issues": ["<short>", ...]}'
)

_VISION_SYSTEM = (
    "You are a strict, fair verifier of a completed real-world task. Judge ONLY whether the "
    "attached photo or video credibly demonstrates that the task described below was completed "
    "as required. Be exacting: vague framing, edited or staged-looking media, wrong activity, "
    "or anything inconclusive fails or requires re-proof. "
    'Respond with ONLY a JSON object: {"verdict": "pass"|"fail"|"re_proof", '
    '"confidence": <0-100 integer>, "reasoning": "<one sentence>", "issues": ["<short>", ...]}'
)

_ALLOWED = {PASS, FAIL, RE_PROOF}


def _parse_verdict(raw: str) -> VerdictResult:
    text = raw.strip()
    if text.startswith("```"):
        # strip a ```json ... ``` fence
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    try:
        data = json.loads(text)
        verdict = str(data["verdict"]).lower()
        if verdict not in _ALLOWED:
            raise ValueError("verdict out of range")
        confidence = data.get("confidence")
        confidence = int(confidence) if confidence is not None else None
        return VerdictResult(
            verdict=verdict,
            confidence=confidence,
            reasoning=str(data.get("reasoning", "")),
            issues=[str(i) for i in data.get("issues", [])],
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        # an unparseable verdict can't be trusted -> demand re-proof
        return VerdictResult(
            RE_PROOF, None, "verifier response was not valid JSON", ["unparseable verdict"]
        )


async def verify_honor(report: str, task: Task, provider: LLMProvider) -> VerdictResult:
    messages = [
        ChatMessage(role="system", content=_HONOR_SYSTEM),
        ChatMessage(
            role="user",
            content=f"TASK: {task.description}\nHONOR REPORT:\n{report}",
        ),
    ]
    result = await provider.chat(messages)
    return _parse_verdict(result.content)


async def verify_media(
    task: Task, *, media_uri: str, provider: LLMProvider, settings: Settings
) -> VerdictResult:
    """Verify a photo/video submission with the configured vision model.

    Called at settle time (never by ``verify``, which queues media proofs when vision is on).
    """
    if not settings.vision_enabled:
        # No vision model -> honor system for media: auto-pass (unchanged behavior).
        return VerdictResult(PASS, None, "no vision model configured — auto-passed", [])
    if not provider.supports_vision:
        return VerdictResult(
            PENDING_REVIEW,
            None,
            "vision model configured but provider lacks vision support",
            ["provider lacks vision"],
        )
    messages = [
        ChatMessage(role="system", content=_VISION_SYSTEM),
        ChatMessage(
            role="user",
            content=f"TASK: {task.description}\nJudge the submitted media.",
            images=[media_uri],
        ),
    ]
    # Errors from the judge propagate: settle_backlog owns retry/transient handling.
    result = await provider.chat(messages, model=settings.vision_model)
    return _parse_verdict(result.content)


async def verify(
    task: Task,
    *,
    report: str,
    timer: TaskTimer | None,
    provider: LLMProvider,
    settings: Settings,
) -> VerdictResult:
    """Route a proof to its verification strategy by the task's proof requirement."""
    pr = task.proof_requirement
    if pr is ProofRequirement.NONE:
        return verify_none()
    if pr is ProofRequirement.TIMER:
        if timer is None:
            return VerdictResult(RE_PROOF, None, "no timer recorded", ["timer missing"])
        return verify_timer(timer)
    if pr is ProofRequirement.HONOR:
        return await verify_honor(report, task, provider)
    if pr in (ProofRequirement.PHOTO, ProofRequirement.VIDEO):
        if settings.vision_enabled:
            return VerdictResult(
                PENDING_REVIEW, None, "media proof queued for her review", ["pending review"]
            )
        return VerdictResult(PASS, None, "no vision model configured — auto-passed", [])
