from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.enums import KinkRating
from app.db.models.profile import KinkEntry
from app.safety import service as safety_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_set_hiatus_toggles_and_freezes(session):
    p = await _profile(session)
    state = await safety_svc.set_hiatus(session, p.id, True)
    assert state.on_hiatus is True
    assert await safety_svc.is_frozen(session, p.id) is True
    state = await safety_svc.set_hiatus(session, p.id, False)
    assert state.on_hiatus is False


async def test_lower_limit_upserts_to_stricter_rating(session):
    p = await _profile(session)
    # first time: creates the entry as a hard limit
    await safety_svc.lower_limit(session, p.id, kink="wax", rating=KinkRating.HARD_LIMIT)
    entry = (await session.execute(
        select(KinkEntry).where(KinkEntry.profile_id == p.id, KinkEntry.kink == "wax")
    )).scalar_one()
    assert entry.rating is KinkRating.HARD_LIMIT


async def test_lower_limit_rejects_non_limit_ratings(session):
    p = await _profile(session)
    with pytest.raises(ValueError):
        await safety_svc.lower_limit(session, p.id, kink="wax", rating=KinkRating.FAVORITE)


async def test_consent_check_due_and_record(session):
    p = await _profile(session)
    state = await safety_svc.get_or_create_state(session, p.id)
    assert safety_svc.consent_check_due(state) is True  # never checked
    await safety_svc.record_consent_check(session, p.id)
    state = await safety_svc.get_or_create_state(session, p.id)
    assert safety_svc.consent_check_due(state) is False
    # due again once the interval has elapsed
    state.last_consent_check_at = datetime.now(timezone.utc) - timedelta(days=60)
    assert safety_svc.consent_check_due(state) is True
