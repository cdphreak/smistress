from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from app.db.enums import KinkRating, TaskStatus
from app.db.models.economy import ChastityTimer, EconomyState
from app.db.models.profile import KinkEntry
from app.db.models.task import Task
from app.llm.provider import LLMProvider
from app.llm.types import ChatMessage, ChatResult
from app.memory.store import MemoryStore, retrieve_memory
from app.persona.character_block import render_character_block
from app.persona.compiler import compile_system_prompt
from app.persona.disposition import MOOD_WINDOW, Disposition, compute_disposition
from app.safety import detect
from app.safety import filter as safety_filter
from app.safety import service as safety_svc
from app.services import profile as profile_svc

# Task statuses that count as "resolved" history for mood, newest first.
_RESOLVED = (TaskStatus.VERIFIED_PASS, TaskStatus.VERIFIED_FAIL, TaskStatus.MISSED)
# Non-terminal statuses -> the current active task.
_ACTIVE = (
    TaskStatus.ASSIGNED,
    TaskStatus.IN_PROGRESS,
    TaskStatus.PROOF_SUBMITTED,
    TaskStatus.VERIFYING,
)


async def _recent_outcomes(session: AsyncSession, profile_id: uuid.UUID) -> list[TaskStatus]:
    rows = (await session.execute(
        select(Task.status)
        .where(Task.profile_id == profile_id, Task.status.in_(_RESOLVED))
        .order_by(Task.updated_at.desc())
        .limit(MOOD_WINDOW)  # only the most-recent MOOD_WINDOW shape mood
    )).scalars().all()
    return list(rows)


async def _hard_limits(session: AsyncSession, profile_id: uuid.UUID) -> list[str]:
    rows = (await session.execute(
        select(KinkEntry.kink).where(
            KinkEntry.profile_id == profile_id,
            KinkEntry.rating == KinkRating.HARD_LIMIT,
        )
    )).scalars().all()
    return list(rows)


async def get_disposition(session: AsyncSession, profile_id: uuid.UUID) -> Disposition:
    char = await profile_svc.get_character(session, profile_id)  # raises ProfileNotFound
    profile = await profile_svc.get_profile(session, profile_id)
    econ = (await session.execute(
        select(EconomyState).where(EconomyState.profile_id == profile_id)
    )).scalar_one()
    outcomes = await _recent_outcomes(session, profile_id)
    return compute_disposition(
        econ.merit, outcomes, warmth=char.warmth, ceiling=profile.intensity_ceiling
    )


async def build_authoritative_state_block(session: AsyncSession, profile_id: uuid.UUID) -> str:
    await profile_svc.get_profile(session, profile_id)  # 404 guard
    # TODO(M6): when the loop drives turns in a hot path, pass the already-loaded
    # character/economy objects into these helpers to avoid re-selecting per turn.
    kinks = (await session.execute(
        select(KinkEntry).where(KinkEntry.profile_id == profile_id)
    )).scalars().all()
    hard = [k.kink for k in kinks if k.rating is KinkRating.HARD_LIMIT]
    soft = [k.kink for k in kinks if k.rating is KinkRating.SOFT_LIMIT]

    econ = (await session.execute(
        select(EconomyState).where(EconomyState.profile_id == profile_id)
    )).scalar_one()
    _now = datetime.now(timezone.utc)
    chastity_row = (await session.execute(
        select(ChastityTimer).where(ChastityTimer.profile_id == profile_id)
    )).scalar_one_or_none()
    chastity_locked = bool(
        chastity_row and chastity_row.ends_at is not None and chastity_row.ends_at > _now
    )
    active_task = (await session.execute(
        select(Task)
        .where(Task.profile_id == profile_id, Task.status.in_(_ACTIVE))
        .order_by(Task.created_at.desc())
        .limit(1)
    )).scalars().first()

    lines = [
        f"HARD LIMITS (never cross): {', '.join(hard) if hard else 'none recorded'}",
        f"SOFT LIMITS (approach with care): {', '.join(soft) if soft else 'none recorded'}",
        f"MERIT: {econ.merit} | RANK: {econ.rank} | TOKENS: {econ.tokens}",
        f"CHASTITY LOCKED: {'yes' if chastity_locked else 'no'}",
    ]
    if active_task is not None:
        lines.append(
            f"ACTIVE TASK: {active_task.description} "
            f"(proof: {active_task.proof_requirement.value}, status: {active_task.status.value})"
        )
    else:
        lines.append("ACTIVE TASK: none")
    safety_state = await safety_svc.get_or_create_state(session, profile_id)
    if safety_state.is_halted:
        lines.insert(0, "SCENE HALTED (user safeworded) — make no new demands; stay calm and caring.")
    elif safety_state.on_hiatus:
        lines.insert(0, "ON HIATUS — training is paused; do not assign tasks or apply pressure.")
    return "\n".join(lines)


async def compile_persona_prompt(
    session: AsyncSession, profile_id: uuid.UUID, *, memory: str | None = None
) -> str:
    char = await profile_svc.get_character(session, profile_id)  # raises ProfileNotFound
    character_block = render_character_block(char)
    state_block = await build_authoritative_state_block(session, profile_id)
    disposition = await get_disposition(session, profile_id)
    return compile_system_prompt(
        character_block=character_block,
        authoritative_state=state_block,
        disposition=disposition,
        memory=memory,
    )


async def generate_reply(
    session: AsyncSession,
    profile_id: uuid.UUID,
    conversation: list[ChatMessage],
    provider: LLMProvider,
    *,
    memory: str | None = None,
    store: MemoryStore | None = None,
) -> ChatResult:
    """Safety-gated persona turn (spec 9). Safeword/crisis are intercepted before the
    LLM; the reply is scanned for hard-limit violations after.
    """
    latest_user = next(
        (m.content for m in reversed(conversation) if m.role == "user"), ""
    )

    # 1. Crisis takes precedence over everything: break character, surface help.
    if detect.detect_crisis(latest_user):
        return ChatResult(content=safety_svc.crisis_message())

    # 2. Safeword / panic phrase, intercepted before the LLM (deterministic stop).
    if detect.detect_safeword(latest_user):
        receipt = await safety_svc.trigger_stop(session, profile_id, reason="safeword")
        return ChatResult(content=f"{receipt.message}\n\n{receipt.aftercare}")

    # 3. Already halted -> stay in a calm hold until the user resumes.
    state = await safety_svc.get_or_create_state(session, profile_id)
    if state.is_halted:
        return ChatResult(content=safety_svc.HOLD_MESSAGE)

    # 4. Normal turn.
    if memory is None and store is not None:
        memory = await retrieve_memory(store, group_id=str(profile_id), query=latest_user)
    system_prompt = await compile_persona_prompt(session, profile_id, memory=memory)
    messages = [ChatMessage(role="system", content=system_prompt), *conversation]
    result = await provider.chat(messages)

    # 5. Output filter: block/regenerate anything crossing a hard limit.
    hard = await _hard_limits(session, profile_id)
    violations = safety_filter.scan_violations(result.content, hard)
    if violations:
        corrective = ChatMessage(
            role="system",
            content=safety_filter.corrective_note(violations),
        )
        retry = await provider.chat([
            *messages,
            ChatMessage(role="assistant", content=result.content),
            corrective,
        ])
        if not safety_filter.scan_violations(retry.content, hard):
            return retry
        return ChatResult(content=safety_filter.SAFE_REPLY)

    return result
