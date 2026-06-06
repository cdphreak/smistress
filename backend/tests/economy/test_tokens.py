import pytest

from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_grant_then_spend_tokens(session):
    p = await _profile(session)
    econ = await econ_svc.grant_tokens(session, p.id, 3)
    await session.commit()
    assert econ.tokens == 3

    econ = await econ_svc.spend_tokens(session, p.id, 2)
    await session.commit()
    assert econ.tokens == 1


async def test_spend_more_than_held_raises_and_does_not_go_negative(session):
    p = await _profile(session)
    await econ_svc.grant_tokens(session, p.id, 1)
    await session.commit()
    with pytest.raises(econ_svc.InsufficientTokens):
        await econ_svc.spend_tokens(session, p.id, 5)
    econ = await econ_svc.get_economy(session, p.id)
    assert econ.tokens == 1
