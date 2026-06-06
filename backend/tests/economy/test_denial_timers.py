from datetime import datetime, timedelta, timezone

from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_set_and_list_active_denial_timer(session):
    p = await _profile(session)
    ends = datetime.now(timezone.utc) + timedelta(hours=4)
    timer = await econ_svc.set_denial_timer(session, p.id, reason="missed task", ends_at=ends)
    await session.commit()
    assert timer.active is True

    active = await econ_svc.active_denial_timers(session, p.id)
    assert len(active) == 1
    assert active[0].reason == "missed task"


async def test_clear_deactivates_all_active(session):
    p = await _profile(session)
    ends = datetime.now(timezone.utc) + timedelta(hours=1)
    await econ_svc.set_denial_timer(session, p.id, reason="a", ends_at=ends)
    await econ_svc.set_denial_timer(session, p.id, reason="b", ends_at=ends)
    await session.commit()

    cleared = await econ_svc.clear_denial_timers(session, p.id)
    await session.commit()
    assert cleared == 2
    assert await econ_svc.active_denial_timers(session, p.id) == []
