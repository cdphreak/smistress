from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.enums import LLMAvailability
from app.db.models.availability import LlmHeartbeat

# Re-declared here (not imported from app.main) to avoid an import cycle.
_settings = Settings()


@dataclass
class AvailabilitySnapshot:
    state: LLMAvailability
    last_heartbeat_at: datetime | None

    @property
    def online(self) -> bool:
        return self.state is LLMAvailability.ONLINE


async def _get_or_create(session: AsyncSession) -> LlmHeartbeat:
    """The single system-wide availability row. Created lazily on first use."""
    row = (await session.execute(select(LlmHeartbeat))).scalars().first()
    if row is None:
        row = LlmHeartbeat()
        session.add(row)
        await session.flush()
    return row


async def record_heartbeat(
    session: AsyncSession, *, source: str = ""
) -> LlmHeartbeat:
    """The home-box agent reported in. Stamps the single row with now. Caller commits."""
    row = await _get_or_create(session)
    row.last_heartbeat_at = datetime.now(timezone.utc)
    row.source = source
    await session.flush()
    return row


async def snapshot(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    ttl_seconds: int | None = None,
) -> AvailabilitySnapshot:
    """Current availability: ONLINE iff the last heartbeat is fresher than the TTL."""
    now = now or datetime.now(timezone.utc)
    ttl = _settings.heartbeat_ttl_seconds if ttl_seconds is None else ttl_seconds
    row = (await session.execute(select(LlmHeartbeat))).scalars().first()
    last = row.last_heartbeat_at if row else None
    if last is not None and (now - last).total_seconds() <= ttl:
        return AvailabilitySnapshot(LLMAvailability.ONLINE, last)
    return AvailabilitySnapshot(LLMAvailability.OFFLINE, last)


async def is_online(session: AsyncSession, *, now: datetime | None = None) -> bool:
    return (await snapshot(session, now=now)).online
