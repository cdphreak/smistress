from httpx import ASGITransport, AsyncClient

from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.main import app, get_provider


async def test_health_reports_ok_and_vision_flag():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "vision_enabled" in body


async def test_llm_ping_uses_injected_provider():
    app.dependency_overrides[get_provider] = lambda: MockLLMProvider(
        scripted=[ChatResult(content="pong")]
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            r = await ac.post("/llm/ping")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["content"] == "pong"
