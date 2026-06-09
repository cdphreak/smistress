from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_adjust_debt_never_negative(session):
    p = await _profile(session)
    await econ_svc.adjust_debt(session, p.id, 20)
    econ = await econ_svc.adjust_debt(session, p.id, -50)
    assert econ.debt == 0


async def test_buy_down_spends_tokens_at_rate_no_merit(session):
    p = await _profile(session)
    await econ_svc.adjust_debt(session, p.id, 10)
    await econ_svc.grant_tokens(session, p.id, 100)
    before_merit = (await econ_svc.get_economy(session, p.id)).merit
    econ = await econ_svc.buy_down_debt(session, p.id, debt_points=4)
    assert econ.debt == 6
    assert econ.tokens == 88
    assert econ.merit == before_merit


async def test_buy_down_capped_by_debt_and_tokens(session):
    p = await _profile(session)
    await econ_svc.adjust_debt(session, p.id, 5)
    await econ_svc.grant_tokens(session, p.id, 6)
    econ = await econ_svc.buy_down_debt(session, p.id, debt_points=5)
    assert econ.debt == 3
    assert econ.tokens == 0
