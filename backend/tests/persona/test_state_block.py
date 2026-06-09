from app.db.enums import SupervisionMode
from app.persona import service as persona_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from app.supervision import service as sup_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_state_block_shows_supervision_mode_and_note(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.HOMEOFFICE)
    await sup_svc.set_note(session, p.id, SupervisionMode.HOMEOFFICE, "meetings till 5")
    block = await persona_svc.build_authoritative_state_block(session, p.id)
    assert "SUPERVISION: homeoffice" in block
    assert "meetings till 5" in block


async def test_state_block_vacation_directive(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.VACATION)
    block = await persona_svc.build_authoritative_state_block(session, p.id)
    assert "vacation" in block.lower()
    assert "paused" in block.lower()
