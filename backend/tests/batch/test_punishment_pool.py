from app.db.enums import PunishmentType
from app.db.models.batch import PunishmentPoolItem
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_punishment_pool_item_round_trip(session):
    p = await _profile(session)
    item = PunishmentPoolItem(
        profile_id=p.id, type=PunishmentType.PENANCE_TASK, severity=2,
        reason="Write 30 lines: I will not keep her waiting.",
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)
    assert item.consumed is False
    assert item.type is PunishmentType.PENANCE_TASK
    assert item.severity == 2
