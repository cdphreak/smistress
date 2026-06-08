from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models.availability import LlmHeartbeat


async def test_heartbeat_row_persists_and_allows_null_timestamp(session):
    row = LlmHeartbeat()  # fresh row: no heartbeat yet
    session.add(row)
    await session.flush()
    assert row.last_heartbeat_at is None
    assert row.source == ""

    row.last_heartbeat_at = datetime.now(timezone.utc)
    row.source = "ollama:qwen"
    await session.flush()

    fetched = (await session.execute(select(LlmHeartbeat))).scalar_one()
    assert fetched.source == "ollama:qwen"
    assert fetched.last_heartbeat_at is not None
