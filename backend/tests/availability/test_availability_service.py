from datetime import datetime, timedelta, timezone

from app.availability import service as avail_svc
from app.db.enums import LLMAvailability


async def test_no_heartbeat_is_offline(session):
    snap = await avail_svc.snapshot(session)
    assert snap.state is LLMAvailability.OFFLINE
    assert snap.online is False
    assert snap.last_heartbeat_at is None


async def test_fresh_heartbeat_is_online(session):
    await avail_svc.record_heartbeat(session, source="ollama:qwen")
    snap = await avail_svc.snapshot(session)
    assert snap.state is LLMAvailability.ONLINE
    assert snap.online is True
    assert snap.last_heartbeat_at is not None
    assert await avail_svc.is_online(session) is True


async def test_stale_heartbeat_is_offline(session):
    await avail_svc.record_heartbeat(session)
    future = datetime.now(timezone.utc) + timedelta(seconds=120)
    snap = await avail_svc.snapshot(session, now=future, ttl_seconds=90)
    assert snap.state is LLMAvailability.OFFLINE
    assert snap.online is False


async def test_record_heartbeat_is_idempotent_single_row(session):
    from sqlalchemy import func, select

    from app.db.models.availability import LlmHeartbeat

    await avail_svc.record_heartbeat(session)
    await avail_svc.record_heartbeat(session, source="second")
    count = (await session.execute(select(func.count(LlmHeartbeat.id)))).scalar_one()
    assert count == 1  # upserts the same single row
