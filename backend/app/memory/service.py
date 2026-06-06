from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.memory import MemoryEpisode
from app.memory.store import MemoryStore
from app.persona import service as persona_svc


async def enqueue_episode(
    session: AsyncSession,
    profile_id: uuid.UUID,
    *,
    name: str,
    body: str,
    source: str = "text",
    source_description: str = "",
    reference_time: datetime,
) -> MemoryEpisode:
    """Durably queue an episode (transactional outbox). Caller owns the commit."""
    episode = MemoryEpisode(
        profile_id=profile_id,
        name=name,
        body=body,
        source=source,
        source_description=source_description,
        reference_time=reference_time,
    )
    session.add(episode)
    await session.flush()
    return episode


async def drain_outbox(
    session: AsyncSession, store: MemoryStore, *, limit: int = 50
) -> int:
    """Push pending episodes to the store. Returns how many succeeded.

    Failures leave the row 'pending' with an incremented attempt count + error, so
    the next drain retries them (spec 3 'writes queue and retry'). Caller commits.
    """
    pending = (await session.execute(
        select(MemoryEpisode)
        .where(MemoryEpisode.status == "pending")
        .order_by(MemoryEpisode.created_at)
        .limit(limit)
    )).scalars().all()

    pushed = 0
    for ep in pending:
        try:
            await store.add_episode(
                group_id=str(ep.profile_id),
                name=ep.name,
                body=ep.body,
                source=ep.source,
                source_description=ep.source_description,
                reference_time=ep.reference_time,
            )
        except Exception as exc:  # noqa: BLE001 - keep queued for retry
            ep.attempts += 1
            ep.last_error = str(exc)[:500]
            continue
        ep.status = "done"
        pushed += 1
    await session.flush()
    return pushed


async def seed_profile_episode(
    session: AsyncSession, profile_id: uuid.UUID
) -> MemoryEpisode:
    """Seed the initial Graphiti episode from the assembled profile (spec 4).

    Raises profile_svc.ProfileNotFound if the profile does not exist.
    """
    summary = await persona_svc.build_authoritative_state_block(session, profile_id)
    return await enqueue_episode(
        session,
        profile_id,
        name="onboarding profile",
        body=f"Initial sub profile at onboarding:\n{summary}",
        source="text",
        source_description="onboarding",
        reference_time=datetime.now(timezone.utc),
    )
