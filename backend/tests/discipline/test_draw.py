from app.db.enums import PunishmentStatus, PunishmentType
from app.db.models.batch import PunishmentPoolItem
from app.db.models.punishment import Punishment
from app.discipline import service as disc_svc
from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from sqlalchemy import select


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_draw_punishment_prefers_matching_severity_and_consumes(session):
    p = await _profile(session)
    session.add(PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.TOKEN_CONFISCATION, severity=1, reason="light",
    ))
    session.add(PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.PENANCE_TASK, severity=2, reason="match",
    ))
    await session.flush()
    item = await disc_svc.draw_punishment(session, p.id, severity=2)
    assert item is not None and item.severity == 2 and item.reason == "match"
    assert item.consumed is True


async def test_draw_punishment_falls_back_to_any_severity(session):
    p = await _profile(session)
    session.add(PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.PENANCE_TASK, severity=1, reason="only",
    ))
    await session.flush()
    item = await disc_svc.draw_punishment(session, p.id, severity=3)
    assert item is not None and item.reason == "only"


async def test_draw_punishment_none_when_empty(session):
    p = await _profile(session)
    assert await disc_svc.draw_punishment(session, p.id, severity=2) is None


async def test_draw_and_issue_uses_pool_item(session):
    p = await _profile(session)
    session.add(PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.TOKEN_CONFISCATION, severity=2, reason="pooled",
    ))
    await econ_svc.grant_tokens(session, p.id, 100)
    await session.flush()
    pun = await disc_svc.draw_and_issue(session, p.id, severity=2)
    assert pun.type is PunishmentType.TOKEN_CONFISCATION
    assert pun.reason == "pooled"
    assert (await econ_svc.get_economy(session, p.id)).debt == 15  # severity 2


async def test_draw_and_issue_falls_back_when_pool_empty(session):
    p = await _profile(session)
    pun = await disc_svc.draw_and_issue(session, p.id, severity=1)
    assert pun.type is PunishmentType.CHASTITY_EXTENSION  # deterministic fallback
    assert (await econ_svc.chastity_status(session, p.id)).locked is True
