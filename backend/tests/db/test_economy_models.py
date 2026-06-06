from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models.economy import DenialTimer, EconomyState
from app.db.models.profile import SubProfile


async def test_economy_state_defaults(session):
    profile = SubProfile(intensity_ceiling=60)
    session.add(profile)
    await session.flush()
    session.add(EconomyState(profile_id=profile.id))
    await session.commit()

    es = (await session.execute(select(EconomyState))).scalar_one()
    assert es.merit == 0
    assert es.rank == "novice"
    assert es.tokens == 0


async def test_denial_timer_persists(session):
    profile = SubProfile(intensity_ceiling=60)
    session.add(profile)
    await session.flush()
    ends = datetime.now(timezone.utc) + timedelta(hours=2)
    session.add(DenialTimer(profile_id=profile.id, reason="missed task", ends_at=ends))
    await session.commit()

    dt = (await session.execute(select(DenialTimer))).scalar_one()
    assert dt.reason == "missed task"
    assert dt.active is True
