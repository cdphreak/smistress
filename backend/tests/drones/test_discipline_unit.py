from app.db.enums import PunishmentType
from app.discipline import service as disc_svc
from app.drones import service as drone_svc
from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_no_discipline_notice_when_debt_free(session):
    p = await _profile(session)
    notices = await drone_svc.standing_orders(session, p.id)
    assert [n for n in notices if n.unit == "discipline"] == []


async def test_discipline_notice_reports_debt(session):
    p = await _profile(session)
    await econ_svc.adjust_debt(session, p.id, 25)
    notices = await drone_svc.standing_orders(session, p.id)
    discipline = [n for n in notices if n.unit == "discipline"]
    assert any("debt of 25" in n.line.lower() for n in discipline)


async def test_discipline_notice_reports_outstanding_penance(session):
    p = await _profile(session)
    await disc_svc.issue_punishment(
        session, p.id, type=PunishmentType.PENANCE_TASK, severity=1, reason="penance",
    )
    notices = await drone_svc.standing_orders(session, p.id)
    discipline = [n for n in notices if n.unit == "discipline"]
    assert any("penance" in n.line.lower() for n in discipline)
