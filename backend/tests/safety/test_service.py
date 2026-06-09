from datetime import datetime, timedelta, timezone

from app.economy import service as econ_svc
from app.safety import service as safety_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True, intensity_ceiling=80)
    )
    await session.flush()
    return p


async def test_trigger_stop_halts_lifts_chastity_no_merit_penalty(session):
    p = await _profile(session)
    await econ_svc.set_chastity(
        session, p.id, ends_at=datetime.now(timezone.utc) + timedelta(hours=2), note="discipline",
    )
    before = (await econ_svc.get_economy(session, p.id)).merit

    receipt = await safety_svc.trigger_stop(session, p.id)

    assert receipt.scene_halted is True
    assert receipt.denial_lifted == 1  # compat field: 1 chastity lock lifted
    assert receipt.merit_penalty == 0
    assert receipt.aftercare  # non-empty caring text
    state = await safety_svc.get_or_create_state(session, p.id)
    assert state.is_halted is True
    assert state.last_safeword_at is not None
    assert (await econ_svc.get_economy(session, p.id)).merit == before  # unchanged
    assert (await econ_svc.chastity_status(session, p.id)).locked is False  # lifted


async def test_resume_clears_halt(session):
    p = await _profile(session)
    await safety_svc.trigger_stop(session, p.id)
    state = await safety_svc.resume(session, p.id)
    assert state.is_halted is False
    assert await safety_svc.is_frozen(session, p.id) is False


async def test_aftercare_uses_prefs_when_present(session):
    p = await _profile(session)
    from app.schemas.onboarding import PreferencesIn
    await profile_svc.update_preferences(
        session, p.id, PreferencesIn(intensity_ceiling=80, aftercare_prefs="tea and quiet"),
    )
    receipt = await safety_svc.trigger_stop(session, p.id)
    assert "tea and quiet" in receipt.aftercare


async def test_crisis_message_breaks_character_with_resources(session):
    msg = safety_svc.crisis_message()
    assert "988" in msg or "help" in msg.lower()
