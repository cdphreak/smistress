from httpx import ASGITransport, AsyncClient

from app.db.session import get_session
from app.main import app


async def test_db_health_ok(session):
    app.dependency_overrides[get_session] = lambda: session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            r = await ac.get("/db/health")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json() == {"database": "ok"}
