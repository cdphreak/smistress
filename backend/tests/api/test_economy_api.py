import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.session import get_session
from app.main import app


@pytest_asyncio.fixture
async def client(session):
    app.dependency_overrides[get_session] = lambda: session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _new_profile(client) -> str:
    r = await client.post(
        "/onboarding/profile", json={"is_adult": True, "consent_acknowledged": True}
    )
    return r.json()["id"]


async def test_standing_defaults(client):
    pid = await _new_profile(client)
    r = await client.get(f"/profile/{pid}/standing")
    assert r.status_code == 200
    body = r.json()
    assert body["merit"] == 0
    assert body["rank"] == "novice"
    assert body["tokens"] == 0
    assert body["denial_timers"] == []


async def test_grant_and_spend_tokens(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/tokens/grant", json={"amount": 3})
    assert r.status_code == 200 and r.json()["tokens"] == 3
    r = await client.post(f"/profile/{pid}/tokens/spend", json={"amount": 5})
    assert r.status_code == 409  # insufficient


async def test_set_and_clear_denial_timer(client):
    pid = await _new_profile(client)
    ends = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    r = await client.post(f"/profile/{pid}/denial-timer", json={"reason": "missed", "ends_at": ends})
    assert r.status_code == 201
    r = await client.get(f"/profile/{pid}/standing")
    assert len(r.json()["denial_timers"]) == 1
    r = await client.post(f"/profile/{pid}/denial-timer/clear")
    assert r.status_code == 200 and r.json()["cleared"] == 1


async def test_standing_404(client):
    r = await client.get(f"/profile/{uuid.uuid4()}/standing")
    assert r.status_code == 404
