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


async def test_put_kinks_replaces_sheet(client):
    pid = await _new_profile(client)
    r = await client.put(f"/profile/{pid}/kinks", json={"entries": [
        {"kink": "bondage", "rating": "favorite"},
        {"kink": "humiliation", "rating": "soft_limit"},
    ]})
    assert r.status_code == 200
    assert r.json()["count"] == 2

    # full replace: a smaller sheet wins
    r = await client.put(f"/profile/{pid}/kinks", json={"entries": [
        {"kink": "spanking", "rating": "like"},
    ]})
    assert r.status_code == 200
    assert r.json()["count"] == 1


async def test_put_kinks_rejects_bad_rating(client):
    pid = await _new_profile(client)
    r = await client.put(f"/profile/{pid}/kinks", json={"entries": [
        {"kink": "bondage", "rating": "not_a_rating"},
    ]})
    assert r.status_code == 422


async def test_add_and_list_toys(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/toys", json={
        "name": "Apex", "type": "vibrator", "intiface_capable": True,
    })
    assert r.status_code == 201
    assert r.json()["intiface_capable"] is True

    r = await client.get(f"/profile/{pid}/toys")
    assert r.status_code == 200
    toys = r.json()
    assert len(toys) == 1
    assert toys[0]["name"] == "Apex"


async def test_add_and_list_goals(client):
    pid = await _new_profile(client)
    r = await client.post(f"/profile/{pid}/goals", json={
        "title": "Daily posture practice", "description": "10 minutes each morning",
    })
    assert r.status_code == 201
    assert r.json()["status"] == "active"

    r = await client.get(f"/profile/{pid}/goals")
    assert r.status_code == 200
    assert r.json()[0]["title"] == "Daily posture practice"


async def test_upsert_so_context(client):
    pid = await _new_profile(client)
    r = await client.put(f"/profile/{pid}/so-context", json={
        "description": "Training for my partner", "dynamic": "24/7-lite",
    })
    assert r.status_code == 200
    # upsert again updates in place
    r = await client.put(f"/profile/{pid}/so-context", json={"description": "Updated"})
    assert r.status_code == 200
    assert r.json()["description"] == "Updated"


async def test_get_and_update_character(client):
    pid = await _new_profile(client)
    r = await client.get(f"/profile/{pid}/character")
    assert r.status_code == 200
    body = r.json()
    assert body["honorific"] == "Headmistress"
    assert body["strictness"] == 80
    assert body["archetype_blend"] == {"governess": 70, "drill_instructor": 30}

    r = await client.put(f"/profile/{pid}/character", json={"sadism": 65, "name": "Vesper"})
    assert r.status_code == 200
    assert r.json()["sadism"] == 65
    assert r.json()["name"] == "Vesper"
    assert r.json()["strictness"] == 80  # untouched dial unchanged

    # out-of-range dial rejected
    r = await client.put(f"/profile/{pid}/character", json={"wit": 250})
    assert r.status_code == 422


async def test_get_full_profile_assembles_everything(client):
    pid = await _new_profile(client)
    await client.post(f"/profile/{pid}/archetype", json={"answers": {"q1": 4, "q2": 4}})
    await client.put(f"/profile/{pid}/kinks", json={"entries": [
        {"kink": "bondage", "rating": "favorite"},
    ]})
    await client.post(f"/profile/{pid}/toys", json={"name": "Apex", "type": "vibrator"})
    await client.post(f"/profile/{pid}/goals", json={"title": "Practice"})
    await client.put(f"/profile/{pid}/so-context", json={"description": "For my partner"})

    r = await client.get(f"/profile/{pid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == pid
    assert body["archetype_scores"]["submissive"] == 100
    assert body["kinks"][0]["kink"] == "bondage"
    assert body["toys"][0]["name"] == "Apex"
    assert body["goals"][0]["title"] == "Practice"
    assert body["so_context"]["description"] == "For my partner"
    assert body["character"]["honorific"] == "Headmistress"


async def test_get_full_profile_404(client):
    import uuid
    r = await client.get(f"/profile/{uuid.uuid4()}")
    assert r.status_code == 404
