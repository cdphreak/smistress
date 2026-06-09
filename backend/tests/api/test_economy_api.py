import uuid

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
    assert body["debt"] == 0
    assert body["chastity"]["locked"] is False


async def test_grant_and_spend_tokens(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/tokens/grant", json={"amount": 3})
    assert r.status_code == 200 and r.json()["tokens"] == 3
    r = await client.post(f"/profile/{pid}/tokens/spend", json={"amount": 5})
    assert r.status_code == 409  # insufficient


async def test_set_and_lift_chastity(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/chastity", json={"hours": 8, "note": "overnight"})
    assert r.status_code == 200
    assert r.json()["chastity"]["locked"] is True
    assert r.json()["chastity"]["seconds_remaining"] > 0
    r = await client.post(f"/profile/{pid}/chastity/lift")
    assert r.status_code == 200 and r.json()["chastity"]["locked"] is False


async def test_buy_down_debt(client):
    pid = await _new_profile(client)
    # grant tokens, then buy down debt that the discipline unit would normally accrue;
    # here we just verify the endpoint clears as much as tokens allow (no debt -> no-op).
    await client.post(f"/profile/{pid}/tokens/grant", json={"amount": 30})
    r = await client.post(f"/profile/{pid}/debt/buy-down", json={"debt_points": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["debt"] == 0  # had no debt; buy-down is a no-op, tokens untouched
    assert body["tokens"] == 30


async def test_standing_404(client):
    r = await client.get(f"/profile/{uuid.uuid4()}/standing")
    assert r.status_code == 404


async def test_set_chastity_unknown_profile_404(client):
    r = await client.post(f"/profile/{uuid.uuid4()}/chastity", json={"hours": 4})
    assert r.status_code == 404
