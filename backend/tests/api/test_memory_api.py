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


async def test_seed_endpoint_queues_episode(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/memory/seed")
    assert r.status_code == 201
    body = r.json()
    assert body["queued"] == 1
    assert "drained" in body


async def test_seed_endpoint_404(client):
    import uuid
    r = await client.post(f"/profile/{uuid.uuid4()}/memory/seed")
    assert r.status_code == 404
