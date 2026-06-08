import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api import chat as chat_api
from app.db.session import get_session
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.main import app


@pytest_asyncio.fixture
async def client(session):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[chat_api.get_provider] = lambda: MockLLMProvider(
        scripted=[ChatResult(content="Kneel and report, pet.")]
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        await ac.post("/llm/heartbeat", json={"source": "test"})  # live-audience: online
        yield ac
    app.dependency_overrides.clear()


async def _new_profile(client) -> str:
    r = await client.post(
        "/onboarding/profile", json={"is_adult": True, "consent_acknowledged": True}
    )
    assert r.status_code == 201
    return r.json()["id"]


async def test_chat_round_trip_and_history(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/chat", json={"content": "what now?"})
    assert r.status_code == 200
    assert r.json()["role"] == "assistant"
    assert r.json()["content"] == "Kneel and report, pet."

    r = await client.get(f"/profile/{pid}/messages")
    assert r.status_code == 200
    msgs = r.json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]


async def test_dossier_reads_live_status(client):
    pid = await _new_profile(client)
    r = await client.get(f"/profile/{pid}/dossier")
    assert r.status_code == 200
    body = r.json()
    assert body["rank"] == "novice"
    assert body["disposition"]["line"]
    assert body["active_task"] is None


async def test_chat_unknown_profile_404(client):
    r = await client.post(f"/profile/{uuid.uuid4()}/chat", json={"content": "hi"})
    assert r.status_code == 404


async def test_chat_returns_action_card(client):
    pid = await _new_profile(client)
    app.dependency_overrides[chat_api.get_provider] = lambda: MockLLMProvider(
        scripted=[ChatResult(content='Kneel.\n```action\n{"tool":"grant_tokens","amount":2}\n```')]
    )
    r = await client.post(f"/profile/{pid}/chat", json={"content": "reward me"})
    assert r.status_code == 200
    body = r.json()
    assert body["content"] == "Kneel."
    assert body["action"]["tool"] == "grant_tokens"
    assert body["action"]["amount"] == 2


async def test_chat_blocked_when_llm_offline(session):
    # A dedicated client that never sends a heartbeat -> the box is "away".
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[chat_api.get_provider] = lambda: MockLLMProvider(
        scripted=[ChatResult(content="should not be reached")]
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        r = await ac.post(
            "/onboarding/profile",
            json={"is_adult": True, "consent_acknowledged": True},
        )
        pid = r.json()["id"]
        r = await ac.post(f"/profile/{pid}/chat", json={"content": "are you there?"})
    app.dependency_overrides.clear()
    assert r.status_code == 503
    assert "away" in r.json()["detail"].lower()
