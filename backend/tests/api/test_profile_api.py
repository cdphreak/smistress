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


async def test_submit_archetype_returns_scores(client):
    pid = await _new_profile(client)
    answers = {"q1": 4, "q2": 4}  # both 'submissive' statements maxed
    r = await client.post(f"/profile/{pid}/archetype", json={"answers": answers})
    assert r.status_code == 200
    scores = r.json()["scores"]
    assert scores["submissive"] == 100
    assert scores["slave"] == 0


async def test_submit_archetype_rejects_unknown_id(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/archetype", json={"answers": {"bogus": 3}})
    assert r.status_code == 422


async def test_archetype_on_missing_profile_404(client):
    import uuid
    r = await client.post(f"/profile/{uuid.uuid4()}/archetype", json={"answers": {}})
    assert r.status_code == 404
