from app.db.enums import PunishmentStatus, PunishmentType
from app.db.models.punishment import Punishment
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


def _issued(profile_id, debt_amount):
    return Punishment(
        profile_id=profile_id, type=PunishmentType.CHASTITY_EXTENSION, severity=1,
        reason="x", debt_amount=debt_amount, status=PunishmentStatus.ISSUED,
    )


async def test_buy_down_does_not_buy_down_penance(session):
    # Penance must be served, not bought — a buy-down leaves the penance ISSUED.
    p = await _profile(session)
    pen = Punishment(
        profile_id=p.id, type=PunishmentType.PENANCE_TASK, severity=2,
        reason="penance", debt_amount=15, status=PunishmentStatus.ISSUED,
    )
    session.add(pen)
    await session.flush()
    await econ_svc.adjust_debt(session, p.id, 15)
    await econ_svc.grant_tokens(session, p.id, 100)
    await econ_svc.buy_down_debt(session, p.id, debt_points=15)
    await session.refresh(pen)
    assert pen.status is PunishmentStatus.ISSUED  # penance is not bought down


async def test_buy_down_marks_whole_punishments_bought_down_fifo(session):
    p = await _profile(session)
    session.add(_issued(p.id, 5))
    session.add(_issued(p.id, 15))
    await session.flush()
    await econ_svc.adjust_debt(session, p.id, 20)
    await econ_svc.grant_tokens(session, p.id, 100)

    # buy down 5 debt points -> clears exactly the first (5) punishment, not the 15
    await econ_svc.buy_down_debt(session, p.id, debt_points=5)
    rows = (await session.execute(
        select(Punishment).where(Punishment.profile_id == p.id)
        .order_by(Punishment.debt_amount)
    )).scalars().all()
    assert rows[0].status is PunishmentStatus.BOUGHT_DOWN
    assert rows[0].resolved_at is not None
    assert rows[1].status is PunishmentStatus.ISSUED  # 15 not fully covered
