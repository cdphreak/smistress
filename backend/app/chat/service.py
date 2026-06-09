from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import tools
from app.db.enums import TaskStatus
from app.db.models.message import Message
from app.db.models.task import Task
from app.economy import service as econ_svc
from app.llm.provider import LLMProvider
from app.llm.types import ChatMessage
from app.memory.store import MemoryStore
from app.persona import service as persona_svc
from app.services import profile as profile_svc

# Most-recent turns sent back to the model as context (bounds the prompt size).
HISTORY_LIMIT = 20

_ACTIVE = (
    TaskStatus.ASSIGNED,
    TaskStatus.IN_PROGRESS,
    TaskStatus.PROOF_SUBMITTED,
    TaskStatus.VERIFYING,
)


async def list_messages(
    session: AsyncSession, profile_id: uuid.UUID, *, limit: int | None = None
) -> list[Message]:
    stmt = select(Message).where(Message.profile_id == profile_id).order_by(Message.created_at)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows[-limit:]) if limit else list(rows)


async def post_message(
    session: AsyncSession,
    profile_id: uuid.UUID,
    content: str,
    provider: LLMProvider,
    store: MemoryStore,
) -> Message:
    """Persist the user turn, generate the reply over recent history, persist + return it.

    Caller commits. ``generate_reply`` already gates safeword/crisis/hard-limits.
    """
    await profile_svc.get_profile(session, profile_id)  # 404 guard
    session.add(Message(profile_id=profile_id, role="user", content=content))
    await session.flush()

    recent = await list_messages(session, profile_id, limit=HISTORY_LIMIT)
    conversation = [ChatMessage(role=m.role, content=m.content) for m in recent]
    result = await persona_svc.generate_reply(
        session, profile_id, conversation, provider, store=store
    )

    clean, action = tools.parse_action(result.content)
    card = await tools.execute_action(session, profile_id, action) if action else None

    reply = Message(profile_id=profile_id, role="assistant", content=clean, action=card)
    session.add(reply)
    await session.flush()
    return reply


async def build_dossier(session: AsyncSession, profile_id: uuid.UUID) -> dict:
    """Read-only live status: economy + disposition + active task (Addendum A5)."""
    econ = await econ_svc.get_economy(session, profile_id)  # raises EconomyNotFound
    disposition = await persona_svc.get_disposition(session, profile_id)
    chastity = await econ_svc.chastity_status(session, profile_id)
    active = (await session.execute(
        select(Task)
        .where(Task.profile_id == profile_id, Task.status.in_(_ACTIVE))
        .order_by(Task.created_at.desc())
        .limit(1)
    )).scalars().first()
    return {
        "rank": econ.rank,
        "merit": econ.merit,
        "tokens": econ.tokens,
        "disposition": {
            "band": disposition.band.value,
            "line": disposition.line,
            "reason": disposition.reason,
            "standing": disposition.standing,
        },
        "active_task": (
            {"description": active.description, "status": active.status.value}
            if active is not None
            else None
        ),
        "debt": econ.debt,
        "chastity": {
            "locked": chastity.locked,
            "ends_at": chastity.ends_at.isoformat() if chastity.ends_at else None,
            "seconds_remaining": chastity.seconds_remaining,
        },
        # compat: existing frontend reads denial_timers as a count (M4b relabels).
        "denial_timers": 1 if chastity.locked else 0,
    }
