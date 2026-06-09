from app.db.enums import SupervisionMode
from app.db.enums import SupervisionMode as _SM
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from app.supervision import service as sup_svc


def test_supervision_mode_members():
    assert {m.value for m in SupervisionMode} == {
        "full", "discreet", "task", "homeoffice", "vacation"
    }


async def test_profile_defaults_to_full_supervision(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await session.refresh(p)
    assert p.supervision_mode is _SM.FULL
    assert p.supervision_notes == {}


async def test_set_mode_and_economy_frozen(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    assert await sup_svc.economy_frozen(session, p.id) is False
    await sup_svc.set_mode(session, p.id, _SM.VACATION)
    assert (await sup_svc.get_mode(session, p.id)) is _SM.VACATION
    assert await sup_svc.economy_frozen(session, p.id) is True


async def test_set_note_per_mode(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await sup_svc.set_note(session, p.id, _SM.HOMEOFFICE, "back-to-back meetings until 5")
    notes = await sup_svc.get_notes(session, p.id)
    assert notes["homeoffice"] == "back-to-back meetings until 5"
    # setting another mode's note does not clobber the first
    await sup_svc.set_note(session, p.id, _SM.DISCREET, "kids home")
    notes = await sup_svc.get_notes(session, p.id)
    assert notes["homeoffice"] == "back-to-back meetings until 5"
    assert notes["discreet"] == "kids home"
