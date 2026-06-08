from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ProofRequirement
from app.economy import service as econ_svc
from app.loop import service as loop_svc

# Optional fenced directive the persona may append to a reply. Parsed + stripped
# server-side, then executed against the loop/economy. Model-agnostic (no native
# tool-calling), so any provider works and tests stay deterministic.
_ACTION_RE = re.compile(r"```action\s*(\{.*?\})\s*```", re.DOTALL)


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


async def execute_action(session: AsyncSession, profile_id: uuid.UUID, action: dict) -> dict:
    """Execute one tool against the live services; return a card dict (caller commits).

    Bad input never raises — it returns a card carrying an ``error`` so the turn
    still completes and the issue is visible.
    """
    tool = action.get("tool")
    try:
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
        if tool == "set_denial_timer":
            hours = int(action["hours"])
            ends_at = datetime.now(timezone.utc) + timedelta(hours=hours)
            await econ_svc.set_denial_timer(
                session, profile_id, reason=str(action.get("reason", "")), ends_at=ends_at
            )
            return {"tool": "set_denial_timer", "hours": hours, "reason": action.get("reason", "")}
        if tool == "grant_tokens":
            amount = int(action["amount"])
            if amount < 1:
                return {"tool": "grant_tokens", "error": "amount must be >= 1"}
            await econ_svc.grant_tokens(session, profile_id, amount)
            return {"tool": "grant_tokens", "amount": amount, "reason": action.get("reason", "")}
    except (KeyError, ValueError, TypeError) as exc:
        return {"tool": tool or "unknown", "error": str(exc)}
    return {"tool": tool or "unknown", "error": "unknown tool"}
