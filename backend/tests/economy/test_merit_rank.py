import uuid

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


def test_rank_ladder_bands():
    assert econ_svc.rank_for(0) == "novice"
    assert econ_svc.rank_for(20) == "disciplined"
    assert econ_svc.rank_for(50) == "adept"
    assert econ_svc.rank_for(80) == "paragon"
    assert econ_svc.rank_for(-50) == "remedial"


async def test_adjust_merit_clamps_and_recomputes_rank(session):
    p = await _profile(session)
    econ = await econ_svc.adjust_merit(session, p.id, 55)
    await session.commit()
    assert econ.merit == 55
    assert econ.rank == "adept"

    econ = await econ_svc.adjust_merit(session, p.id, 1000)
    await session.commit()
    assert econ.merit == 100
    assert econ.rank == "paragon"

    econ = await econ_svc.adjust_merit(session, p.id, -1000)
    await session.commit()
    assert econ.merit == -100
    assert econ.rank == "remedial"


async def test_get_economy_unknown_profile_raises(session):
    with pytest.raises(econ_svc.EconomyNotFound):
        await econ_svc.get_economy(session, uuid.uuid4())
