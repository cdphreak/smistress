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


async def test_supervision_defaults_to_full(client):
    pid = await _new_profile(client)
    r = await client.get(f"/profile/{pid}/supervision")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "full"
    assert body["notes"] == {}


async def test_set_mode_and_note(client):
    pid = await _new_profile(client)
    r = await client.put(f"/profile/{pid}/supervision/mode", json={"mode": "vacation"})
    assert r.status_code == 200 and r.json()["mode"] == "vacation"
    r = await client.put(
        f"/profile/{pid}/supervision/note",
        json={"mode": "homeoffice", "note": "meetings till 5"},
    )
    assert r.status_code == 200
    assert r.json()["notes"]["homeoffice"] == "meetings till 5"


async def test_set_mode_rejects_unknown(client):
    pid = await _new_profile(client)
    r = await client.put(f"/profile/{pid}/supervision/mode", json={"mode": "nonsense"})
    assert r.status_code == 422


async def test_supervision_404(client):
    r = await client.get(f"/profile/{uuid.uuid4()}/supervision")
    assert r.status_code == 404
