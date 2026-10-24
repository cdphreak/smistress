import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.backlog import get_provider
from app.db.models.availability import LlmHeartbeat
from app.db.session import get_session
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.main import app


@pytest_asyncio.fixture
async def client(session):
    app.dependency_overrides[get_session] = lambda: session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _new_profile(client) -> str:
    return (await client.post("/onboarding/profile", json={
        "is_adult": True, "consent_acknowledged": True,
    })).json()["id"]


async def _force_online(session):
    from datetime import datetime, timezone
    session.add(LlmHeartbeat(last_heartbeat_at=datetime.now(timezone.utc)))
    await session.flush()


async def test_settle_returns_503_when_offline(client, session):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/backlog/settle")
    assert r.status_code == 503
    assert "away" in r.json()["detail"].lower()


async def test_settle_judges_pending_review_proof_when_online(client, session):
    from app.db.models.loop import Proof
    from sqlalchemy import select

    pid = await _new_profile(client)
    # Stage a media proof. Under default Settings (no vision) submit_proof leaves
    # verdict 'pending'; the endpoint serves the vision-enabled path, so flip the
    # row to 'pending_review' to represent a queued-for-review proof:
    tid = (await client.post(f"/profile/{pid}/tasks", json={
        "description": "photo task", "proof_requirement": "photo",
    })).json()["id"]
    await client.post(f"/tasks/{tid}/start")
    await client.post(f"/tasks/{tid}/proof", json={"media_uri": "data:image/png;base64,AAA"})
    proof = (await session.execute(
        select(Proof).where(Proof.task_id == uuid.UUID(tid)).order_by(Proof.created_at.desc())
    )).scalars().first()
    proof.verdict = "pending_review"
    await session.flush()

    await _force_online(session)
    app.dependency_overrides[get_provider] = lambda: MockLLMProvider(
        supports_vision=True, scripted=[ChatResult(
            content='{"verdict": "pass", "confidence": 90, "reasoning": "ok", "issues": []}',
        )]
    )
    try:
        r = await client.post(f"/profile/{pid}/backlog/settle")
    finally:
        app.dependency_overrides.pop(get_provider, None)
    assert r.status_code == 200
    body = r.json()
    assert body["judged"] == 1 and body["passed"] == 1
