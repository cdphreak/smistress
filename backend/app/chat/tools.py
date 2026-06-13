from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.loop import Proof
from app.db.models.task import Task
from app.economy import service as econ_svc
from app.llm.provider import LLMProvider
from app.loop import service as loop_svc

# Optional fenced directive the persona may append to a reply. Parsed + stripped
# server-side, then executed against the loop/economy. Model-agnostic (no native
# tool-calling), so any provider works and tests stay deterministic.
_ACTION_RE = re.compile(r"```action\s*(\{.*?\})\s*```", re.DOTALL)

# Non-terminal task statuses -> the single "active" task a complete_task acts on.
_ACTIVE = (
    TaskStatus.ASSIGNED,
    TaskStatus.IN_PROGRESS,
    TaskStatus.PROOF_SUBMITTED,
    TaskStatus.VERIFYING,
)

# complete_task can only resolve proofs the chat surface can carry: a written
# honor report (or none). Media/timer proofs need the task surface artifact.
_CHAT_CLOSABLE = (ProofRequirement.HONOR, ProofRequirement.NONE)

_settings = Settings()


def parse_action(text: str) -> tuple[str, dict | None]:
    """Return (text_without_block, action_dict_or_None).

    The block is always stripped if present; the action is None when there is no
    block or the JSON is malformed.
    """
    match = _ACTION_RE.search(text)
    if not match:
        return text.strip(), None
    clean = (text[: match.start()] + text[match.end() :]).strip()
    try:
        action = json.loads(match.group(1))
    except json.JSONDecodeError:
        return clean, None
    return clean, action if isinstance(action, dict) else None


async def _complete_task(
    session: AsyncSession, profile_id: uuid.UUID, *, report: str, provider: LLMProvider | None
) -> dict:
    """Close out the profile's active task by running its proof through verification.

    Submits the user's report as proof and runs the existing verify pipeline (the
    honor-report judge), which applies the merit/economy outcome. Honor/none proofs
    only — media/timer proofs are resolved from the task surface.
    """
    if provider is None:
        return {"tool": "complete_task", "error": "no verifier available"}
    active = (await session.execute(
        select(Task)
        .where(Task.profile_id == profile_id, Task.status.in_(_ACTIVE))
        .order_by(Task.created_at.desc())
        .limit(1)
    )).scalars().first()
    if active is None:
        return {"tool": "complete_task", "error": "no active task to complete"}
    if active.proof_requirement not in _CHAT_CLOSABLE:
        return {
            "tool": "complete_task",
            "error": f"task needs {active.proof_requirement.value} proof — "
            "it must be completed from the task surface",
        }
    await loop_svc.submit_proof(session, active.id, report=report)
    task = await loop_svc.verify_task(session, active.id, provider, _settings)
    proof = (await session.execute(
        select(Proof).where(Proof.task_id == active.id).order_by(Proof.created_at.desc())
    )).scalars().first()
    return {
        "tool": "complete_task",
        "task_id": str(task.id),
        "status": task.status.value,
        "verdict": proof.verdict if proof is not None else None,
        "reasoning": proof.reasoning if proof is not None else "",
    }


async def execute_action(
    session: AsyncSession,
    profile_id: uuid.UUID,
    action: dict,
    *,
    report: str = "",
    provider: LLMProvider | None = None,
) -> dict:
    """Execute one tool against the live services; return a card dict (caller commits).

    ``report``/``provider`` are used by ``complete_task`` to verify the user's
    just-submitted proof. Bad input never raises — it returns a card carrying an
    ``error`` so the turn still completes and the issue is visible.
    """
    tool = action.get("tool")
    try:
        if tool == "complete_task":
            return await _complete_task(session, profile_id, report=report, provider=provider)
        if tool == "assign_task":
            # Normalize: capable models often capitalize ("Honor"); the enum is lower-case.
            proof = ProofRequirement(str(action.get("proof", "honor")).strip().lower())
            deadline = None
            if action.get("deadline_hours"):
                deadline = datetime.now(timezone.utc) + timedelta(
                    hours=int(action["deadline_hours"])
                )
            required_seconds = (
                int(action["timer_seconds"]) if action.get("timer_seconds") else None
            )
            task = await loop_svc.assign_task(
                session,
                profile_id,
                description=str(action["description"]),
                proof_requirement=proof,
                deadline=deadline,
                merit_reward=int(action.get("merit_reward", 0)),
                merit_miss_penalty=int(action.get("merit_miss_penalty", 0)),
                required_seconds=required_seconds,
            )
            return {
                "tool": "assign_task",
                "task_id": str(task.id),
                "description": task.description,
                "proof": proof.value,
                "merit_reward": task.merit_reward,
            }
        if tool == "set_chastity":
            hours = int(action["hours"])
            if hours < 1:
                return {"tool": "set_chastity", "error": "hours must be >= 1"}
            await econ_svc.extend_chastity(session, profile_id, hours=hours)
            if action.get("reason"):
                await econ_svc.set_chastity_note(session, profile_id, str(action["reason"]))
            return {"tool": "set_chastity", "hours": hours, "reason": action.get("reason", "")}
        if tool == "grant_tokens":
            amount = int(action["amount"])
            if amount < 1:
                return {"tool": "grant_tokens", "error": "amount must be >= 1"}
            await econ_svc.grant_tokens(session, profile_id, amount)
            return {"tool": "grant_tokens", "amount": amount, "reason": action.get("reason", "")}
    except (KeyError, ValueError, TypeError) as exc:
        return {"tool": tool or "unknown", "error": str(exc)}
    return {"tool": tool or "unknown", "error": "unknown tool"}
