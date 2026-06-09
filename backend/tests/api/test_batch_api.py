import json
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api import chat as chat_api
from app.db.session import get_session
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.main import app


def _payload():
    return ChatResult(content=json.dumps({
        "tasks": [{"description": f"t{i}", "proof": "honor"} for i in range(3)],
        "lines": [{"unit": "assignment", "event": "task_drop", "text": "{task}"}
                  for _ in range(4)],
        "punishments": [
            {"type": "penance_task", "severity": 2, "reason": f"penance {i}"}
            for i in range(3)
        ],
    }))


@pytest_asyncio.fixture
async def client(session):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[chat_api.get_provider] = lambda: MockLLMProvider(
        scripted=[_payload()]
    )
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


async def test_generate_requires_llm_online(client):
    pid = await _new_profile(client)  # no heartbeat -> offline
    r = await client.post(f"/profile/{pid}/batch/generate")
    assert r.status_code == 503


async def test_generate_when_online_persists_and_returns_counts(client):
    pid = await _new_profile(client)
    await client.post("/llm/heartbeat", json={"source": "test"})  # mark online
    r = await client.post(f"/profile/{pid}/batch/generate")
    assert r.status_code == 200
    body = r.json()
    assert body["tasks_added"] == 3
    assert body["lines_added"] == 4
    assert body["punishments_added"] == 3
    s = await client.get(f"/profile/{pid}/batch/status")
    assert s.status_code == 200
    assert s.json()["task_pool"] == 3


async def test_status_reports_low_pools(client):
    pid = await _new_profile(client)
    r = await client.get(f"/profile/{pid}/batch/status")
    assert r.status_code == 200
    assert r.json()["task_pool_low"] is True
    assert r.json()["punishment_pool_low"] is True


async def test_generate_unknown_profile_404(client):
    await client.post("/llm/heartbeat", json={"source": "test"})  # online, so we reach the 404
    r = await client.post(f"/profile/{uuid.uuid4()}/batch/generate")
    assert r.status_code == 404
