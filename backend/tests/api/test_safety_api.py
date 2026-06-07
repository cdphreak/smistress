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
        "/onboarding/profile",
        json={"is_adult": True, "consent_acknowledged": True},
    )
    assert r.status_code == 201
    return r.json()["id"]


async def test_safeword_then_resume(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/safeword")
    assert r.status_code == 200
    body = r.json()
    assert body["scene_halted"] is True
    assert body["merit_penalty"] == 0
    assert body["aftercare"]

    r = await client.get(f"/profile/{pid}/safety")
    assert r.json()["is_halted"] is True

    r = await client.post(f"/profile/{pid}/resume")
    assert r.status_code == 200
    assert r.json()["is_halted"] is False


async def test_hiatus_lower_limit_consent(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/hiatus", json={"on": True})
    assert r.status_code == 200 and r.json()["on_hiatus"] is True

    r = await client.post(f"/profile/{pid}/lower-limit", json={"kink": "wax", "rating": "hard_limit"})
    assert r.status_code == 200 and r.json()["rating"] == "hard_limit"

    r = await client.post(f"/profile/{pid}/lower-limit", json={"kink": "wax", "rating": "favorite"})
    assert r.status_code == 422  # only soft/hard limits accepted

    r = await client.post(f"/profile/{pid}/consent-check")
    assert r.status_code == 200
    r = await client.get(f"/profile/{pid}/safety")
    assert r.json()["consent_check_due"] is False


async def test_delete_everything(client):
    pid = await _new_profile(client)
    r = await client.delete(f"/profile/{pid}")
    assert r.status_code == 204
    r = await client.get(f"/profile/{pid}")
    assert r.status_code == 404


async def test_safety_endpoints_404_on_missing_profile(client):
    r = await client.post(f"/profile/{uuid.uuid4()}/safeword")
    assert r.status_code == 404
