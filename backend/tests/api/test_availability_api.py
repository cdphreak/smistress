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


async def test_availability_starts_offline(client):
    r = await client.get("/llm/availability")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "offline"
    assert body["online"] is False
    assert body["last_heartbeat_at"] is None


async def test_heartbeat_makes_online(client):
    r = await client.post("/llm/heartbeat", json={"source": "ollama:qwen"})
    assert r.status_code == 200
    assert r.json()["online"] is True

    r = await client.get("/llm/availability")
    body = r.json()
    assert body["state"] == "online"
    assert body["online"] is True
    assert body["last_heartbeat_at"] is not None


async def test_heartbeat_accepts_empty_body(client):
    r = await client.post("/llm/heartbeat", json={})
    assert r.status_code == 200
    assert r.json()["online"] is True
