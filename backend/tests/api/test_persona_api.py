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


async def test_get_disposition_returns_band_and_line(client):
    pid = await _new_profile(client)
    r = await client.get(f"/profile/{pid}/disposition")
    assert r.status_code == 200
    body = r.json()
    # merit 0, warmth 30, no history -> raw standing 30, but the default consent
    # ceiling (50) clamps severity up to standing 50 -> neutral band.
    assert body["band"] == "neutral"
    assert body["standing"] == 50
    assert "·" in body["line"]
    assert body["reason"]


async def test_get_disposition_404(client):
    import uuid
    r = await client.get(f"/profile/{uuid.uuid4()}/disposition")
    assert r.status_code == 404
