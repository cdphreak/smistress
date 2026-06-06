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


async def test_get_questionnaire(client):
    r = await client.get("/onboarding/questionnaire")
    assert r.status_code == 200
    body = r.json()
    assert len(body["statements"]) >= 14
    assert "bondage" in body["kinks"]
    assert body["answer_scale"]["max"] == 4


async def test_create_profile_requires_consent_and_adult(client):
    r = await client.post(
        "/onboarding/profile",
        json={"is_adult": True, "consent_acknowledged": False},
    )
    assert r.status_code == 422

    r = await client.post(
        "/onboarding/profile",
        json={"is_adult": True, "consent_acknowledged": True, "intensity_ceiling": 60},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["intensity_ceiling"] == 60
    assert "id" in body
