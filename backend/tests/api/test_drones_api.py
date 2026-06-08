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
    assert r.status_code == 201
    return r.json()["id"]


async def test_standing_orders_returns_assignment_notice(client):
    pid = await _new_profile(client)
    r = await client.get(f"/profile/{pid}/standing-orders")
    assert r.status_code == 200
    notices = r.json()["notices"]
    assert notices[0]["unit"] == "assignment"
    assert "no standing assignment" in notices[0]["line"].lower()


async def test_standing_orders_404_for_unknown_profile(client):
    r = await client.get(f"/profile/{uuid.uuid4()}/standing-orders")
    assert r.status_code == 404
