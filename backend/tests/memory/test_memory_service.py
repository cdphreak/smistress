from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models.memory import MemoryEpisode
from app.memory import service as mem_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from tests.memory.fakes import FakeMemoryStore


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_enqueue_writes_pending_row(session):
    p = await _profile(session)
    await mem_svc.enqueue_episode(
        session, p.id, name="seed", body="hi", source="text",
        source_description="onboarding", reference_time=datetime.now(timezone.utc),
    )
    await session.commit()
    row = (await session.execute(select(MemoryEpisode))).scalar_one()
    assert row.status == "pending"


async def test_drain_pushes_pending_and_marks_done(session):
    p = await _profile(session)
    await mem_svc.enqueue_episode(
        session, p.id, name="seed", body="hi", source="text",
        source_description="onboarding", reference_time=datetime.now(timezone.utc),
    )
    await session.commit()

    store = FakeMemoryStore()
    pushed = await mem_svc.drain_outbox(session, store)
    await session.commit()

    assert pushed == 1
    assert len(store.episodes) == 1
    assert store.episodes[0].group_id == str(p.id)
    row = (await session.execute(select(MemoryEpisode))).scalar_one()
    assert row.status == "done"


async def test_drain_retries_on_failure_keeps_pending(session):
    p = await _profile(session)
    await mem_svc.enqueue_episode(
        session, p.id, name="seed", body="hi", source="text",
        source_description="onboarding", reference_time=datetime.now(timezone.utc),
    )
    await session.commit()

    store = FakeMemoryStore(fail=True)  # FalkorDB down
    pushed = await mem_svc.drain_outbox(session, store)
    await session.commit()

    assert pushed == 0
    row = (await session.execute(select(MemoryEpisode))).scalar_one()
    assert row.status == "pending"      # still queued for retry
    assert row.attempts == 1
    assert row.last_error


async def test_drain_scoped_to_profile_only_drains_that_profile(session):
    p1 = await _profile(session)
    p2 = await _profile(session)
    for p, name in ((p1, "p1-ep"), (p2, "p2-ep")):
        await mem_svc.enqueue_episode(
            session, p.id, name=name, body="x", source="text",
            source_description="t", reference_time=datetime.now(timezone.utc),
        )
    await session.commit()

    store = FakeMemoryStore()
    pushed = await mem_svc.drain_outbox(session, store, profile_id=p1.id)
    await session.commit()

    assert pushed == 1
    assert [e.group_id for e in store.episodes] == [str(p1.id)]
    # p2's episode stays pending
    rows = (await session.execute(select(MemoryEpisode).where(MemoryEpisode.profile_id == p2.id))).scalars().all()
    assert len(rows) == 1 and rows[0].status == "pending"


async def test_drain_global_when_profile_id_none(session):
    p1 = await _profile(session)
    p2 = await _profile(session)
    for p in (p1, p2):
        await mem_svc.enqueue_episode(
            session, p.id, name="ep", body="x", source="text",
            source_description="t", reference_time=datetime.now(timezone.utc),
        )
    await session.commit()

    store = FakeMemoryStore()
    pushed = await mem_svc.drain_outbox(session, store)  # default: global
    await session.commit()
    assert pushed == 2  # backward-compatible
