from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from app.db.models.safety import SafetyState
from sqlalchemy import select


async def test_create_profile_seeds_safety_state(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    state = (await session.execute(
        select(SafetyState).where(SafetyState.profile_id == p.id)
    )).scalar_one()
    assert state.is_halted is False
    assert state.on_hiatus is False
    assert state.last_safeword_at is None
    assert state.last_consent_check_at is None
