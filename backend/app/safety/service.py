from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.safety import SafetyState
from app.economy import service as econ_svc
from app.services import profile as profile_svc

# Calm, out-of-persona copy. The one place the severe styling intentionally softens.
CALM_STOP_MESSAGE = (
    "Okay — we're stopping now. You're safe, and you did nothing wrong. "
    "The scene is over, your timers and denial are cleared, and nothing counts against you."
)
HOLD_MESSAGE = (
    "We're still paused. There's no rush — rest as long as you need. "
    "When you're ready to pick things back up, let me know."
)
CRISIS_MESSAGE = (
    "I'm stepping out of character because what you said matters more than any scene. "
    "You deserve real support right now. If you might be in danger, please contact a crisis "
    "line: in the US call or text 988 (Suicide & Crisis Lifeline), or text HOME to 741741. "
    "If you're elsewhere, your local emergency number can help. I'm here with you."
)


@dataclass
class StopReceipt:
    scene_halted: bool
    denial_lifted: int
    merit_penalty: int
    aftercare: str
    message: str


def aftercare_message(profile) -> str:
    base = (
        "You're safe. Take a slow breath, drink some water, and let yourself come down gently."
    )
    prefs = (profile.aftercare_prefs or "").strip()
    return f"{base} Your aftercare notes: {prefs}." if prefs else base


def crisis_message() -> str:
    return CRISIS_MESSAGE


async def get_or_create_state(
    session: AsyncSession, profile_id: uuid.UUID
) -> SafetyState:
    await profile_svc.get_profile(session, profile_id)  # raises ProfileNotFound
    state = (await session.execute(
        select(SafetyState).where(SafetyState.profile_id == profile_id)
    )).scalar_one_or_none()
    if state is None:  # defensive: profiles created before M8 have no row
        state = SafetyState(profile_id=profile_id)
        session.add(state)
        await session.flush()
    return state


async def trigger_stop(
    session: AsyncSession, profile_id: uuid.UUID, *, reason: str = "safeword"
) -> StopReceipt:
    """Deterministic emergency stop (spec 9). Never depends on the LLM.

    Halts the scene, lifts all denial pressure, applies NO merit penalty.
    Caller commits.
    """
    state = await get_or_create_state(session, profile_id)
    state.is_halted = True
    state.last_safeword_at = datetime.now(timezone.utc)
    lifted = await econ_svc.clear_denial_timers(session, profile_id)
    profile = await profile_svc.get_profile(session, profile_id)
    await session.flush()
    return StopReceipt(
        scene_halted=True,
        denial_lifted=lifted,
        merit_penalty=0,
        aftercare=aftercare_message(profile),
        message=CALM_STOP_MESSAGE,
    )


async def resume(session: AsyncSession, profile_id: uuid.UUID) -> SafetyState:
    state = await get_or_create_state(session, profile_id)
    state.is_halted = False
    await session.flush()
    return state


async def is_frozen(session: AsyncSession, profile_id: uuid.UUID) -> bool:
    """Halted (safeword) or on hiatus -> the loop must not penalize (spec 9)."""
    state = await get_or_create_state(session, profile_id)
    return state.is_halted or state.on_hiatus
