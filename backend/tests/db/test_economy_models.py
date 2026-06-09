from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models.economy import EconomyState
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
    from app.db.models.economy import DenialTimer  # noqa: F401 — removed in M4a; fixed later

    profile = SubProfile(intensity_ceiling=60)
    session.add(profile)
    await session.flush()
    ends = datetime.now(timezone.utc) + timedelta(hours=2)
    session.add(DenialTimer(profile_id=profile.id, reason="missed task", ends_at=ends))
    await session.commit()

    dt = (await session.execute(select(DenialTimer))).scalar_one()
    assert dt.reason == "missed task"
    assert dt.active is True


async def test_chastity_timer_is_single_per_profile(session):
    from datetime import datetime, timedelta, timezone

    from app.db.models.economy import ChastityTimer
    from app.schemas.onboarding import ProfileCreate
    from app.services import profile as profile_svc

    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    ends = datetime.now(timezone.utc) + timedelta(hours=8)
    timer = ChastityTimer(profile_id=p.id, ends_at=ends, note="overnight")
    session.add(timer)
    await session.flush()
    await session.refresh(timer)
    assert timer.ends_at == ends
    assert timer.note == "overnight"


async def test_economy_state_has_debt_defaulting_zero(session):
    from sqlalchemy import select

    from app.db.models.economy import EconomyState
    from app.schemas.onboarding import ProfileCreate
    from app.services import profile as profile_svc

    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    econ = (await session.execute(
        select(EconomyState).where(EconomyState.profile_id == p.id)
    )).scalar_one()
    assert econ.debt == 0


async def test_punishment_round_trip(session):
    from app.db.enums import PunishmentStatus, PunishmentType
    from app.db.models.punishment import Punishment
    from app.schemas.onboarding import ProfileCreate
    from app.services import profile as profile_svc

    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    pun = Punishment(
        profile_id=p.id, type=PunishmentType.CHASTITY_EXTENSION, severity=2,
        reason="missed posture drill", debt_amount=15, status=PunishmentStatus.ISSUED,
    )
    session.add(pun)
    await session.flush()
    await session.refresh(pun)
    assert pun.status is PunishmentStatus.ISSUED
    assert pun.penance_task_id is None
    assert pun.resolved_at is None
