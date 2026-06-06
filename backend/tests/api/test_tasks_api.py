import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.tasks import get_task_provider
from app.db.session import get_session
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
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


async def test_assign_list_get_task(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/tasks", json={
        "description": "make the bed", "proof_requirement": "honor", "merit_reward": 5,
    })
    assert r.status_code == 201
    tid = r.json()["id"]
    assert r.json()["status"] == "assigned"

    r = await client.get(f"/profile/{pid}/tasks")
    assert r.status_code == 200 and len(r.json()) == 1

    r = await client.get(f"/tasks/{tid}")
    assert r.status_code == 200 and r.json()["description"] == "make the bed"


async def test_full_honor_loop_via_api(client):
    pid = await _new_profile(client)
    tid = (await client.post(f"/profile/{pid}/tasks", json={
        "description": "20 push-ups", "proof_requirement": "honor",
    })).json()["id"]

    assert (await client.post(f"/tasks/{tid}/start")).status_code == 200
    assert (await client.post(f"/tasks/{tid}/proof", json={"report": "did all twenty"})).status_code == 200

    app.dependency_overrides[get_task_provider] = lambda: MockLLMProvider(scripted=[ChatResult(
        content='{"verdict": "pass", "confidence": 88, "reasoning": "ok", "issues": []}'
    )])
    try:
        r = await client.post(f"/tasks/{tid}/verify")
    finally:
        app.dependency_overrides.pop(get_task_provider, None)
    assert r.status_code == 200
    assert r.json()["status"] == "verified_pass"


async def test_task_404(client):
    r = await client.get(f"/tasks/{uuid.uuid4()}")
    assert r.status_code == 404
