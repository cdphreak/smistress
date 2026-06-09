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


async def test_unlocked_by_default(session):
    p = await _profile(session)
    status = await econ_svc.chastity_status(session, p.id)
    assert status.locked is False
    assert status.ends_at is None
    assert status.seconds_remaining == 0


async def test_set_then_locked_with_remaining(session):
    p = await _profile(session)
    now = datetime.now(timezone.utc)
    await econ_svc.set_chastity(session, p.id, ends_at=now + timedelta(hours=4), note="lock")
    status = await econ_svc.chastity_status(session, p.id, now=now)
    assert status.locked is True
    assert 14000 < status.seconds_remaining <= 14400


async def test_extend_pushes_release_out(session):
    p = await _profile(session)
    now = datetime.now(timezone.utc)
    await econ_svc.set_chastity(session, p.id, ends_at=now + timedelta(hours=2))
    await econ_svc.extend_chastity(session, p.id, hours=3, now=now)
    status = await econ_svc.chastity_status(session, p.id, now=now)
    assert 17900 < status.seconds_remaining <= 18000


async def test_extend_from_unlocked_starts_from_now(session):
    p = await _profile(session)
    now = datetime.now(timezone.utc)
    await econ_svc.extend_chastity(session, p.id, hours=6, now=now)
    status = await econ_svc.chastity_status(session, p.id, now=now)
    assert status.locked is True
    assert 21500 < status.seconds_remaining <= 21600


async def test_lift_unlocks(session):
    p = await _profile(session)
    now = datetime.now(timezone.utc)
    await econ_svc.set_chastity(session, p.id, ends_at=now + timedelta(hours=4))
    await econ_svc.lift_chastity(session, p.id)
    assert (await econ_svc.chastity_status(session, p.id)).locked is False


async def test_elapsed_lock_reads_as_unlocked(session):
    p = await _profile(session)
    now = datetime.now(timezone.utc)
    await econ_svc.set_chastity(session, p.id, ends_at=now - timedelta(minutes=1))
    status = await econ_svc.chastity_status(session, p.id, now=now)
    assert status.locked is False
    assert status.seconds_remaining == 0
