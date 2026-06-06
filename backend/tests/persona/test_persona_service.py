import pytest

from app.db.enums import KinkRating, ProofRequirement, TaskStatus
from app.db.models.economy import EconomyState
from app.db.models.task import Task
from app.persona import service as persona_svc
from app.persona.disposition import DispositionBand
from app.schemas.onboarding import KinkItem, ProfileCreate
from app.services import profile as profile_svc


async def _profile(session, *, ceiling=100):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True, intensity_ceiling=ceiling)
    )
    await session.flush()
    return p


async def _econ_id(session, profile_id):
    from sqlalchemy import select
    return (await session.execute(
        select(EconomyState.id).where(EconomyState.profile_id == profile_id)
    )).scalar_one()


async def test_get_disposition_reads_merit_and_recent_outcomes(session):
    p = await _profile(session)
    econ = await session.get(EconomyState, (await _econ_id(session, p.id)))
    econ.merit = -100
    session.add_all([
        Task(profile_id=p.id, description="a", proof_requirement=ProofRequirement.HONOR,
             status=TaskStatus.MISSED),
        Task(profile_id=p.id, description="b", proof_requirement=ProofRequirement.HONOR,
             status=TaskStatus.MISSED),
    ])
    await session.commit()

    disp = await persona_svc.get_disposition(session, p.id)
    assert disp.band is DispositionBand.SEVERE
    assert "2 recent misses" in disp.reason


async def test_authoritative_state_block_carries_limits_and_economy(session):
    p = await _profile(session)
    await profile_svc.replace_kinks(session, p.id, [
        KinkItem(kink="blood", rating=KinkRating.HARD_LIMIT),
        KinkItem(kink="wax", rating=KinkRating.SOFT_LIMIT),
    ])
    await session.commit()

    block = await persona_svc.build_authoritative_state_block(session, p.id)
    assert "blood" in block          # hard limit verbatim
    assert "wax" in block            # soft limit verbatim
    assert "MERIT" in block.upper()


async def test_compile_persona_prompt_contains_identity_limits_and_disposition(session):
    p = await _profile(session)
    await profile_svc.replace_kinks(session, p.id, [
        KinkItem(kink="blood", rating=KinkRating.HARD_LIMIT),
    ])
    await session.commit()

    prompt = await persona_svc.compile_persona_prompt(session, p.id)
    assert "Headmistress" in prompt        # character identity
    assert "blood" in prompt               # hard limit verbatim
    assert "CURRENT DISPOSITION" in prompt
    assert "SAFETY" in prompt


async def test_compile_persona_prompt_404(session):
    import uuid
    with pytest.raises(profile_svc.ProfileNotFound):
        await persona_svc.compile_persona_prompt(session, uuid.uuid4())
