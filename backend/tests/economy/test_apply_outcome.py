from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.task import Task
from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def _resolved_task(session, profile_id, status, *, reward=0, fail=0, miss=0):
    t = Task(
        profile_id=profile_id, description="t", proof_requirement=ProofRequirement.HONOR,
        status=status, merit_reward=reward, merit_fail_penalty=fail, merit_miss_penalty=miss,
    )
    session.add(t)
    await session.flush()
    return t


async def test_pass_adds_reward(session):
    p = await _profile(session)
    t = await _resolved_task(session, p.id, TaskStatus.VERIFIED_PASS, reward=10)
    econ = await econ_svc.apply_task_outcome(session, t)
    await session.commit()
    assert econ.merit == 10  # first pass -> streak multiplier x1.0


async def test_fail_subtracts_penalty(session):
    p = await _profile(session)
    t = await _resolved_task(session, p.id, TaskStatus.VERIFIED_FAIL, fail=7)
    econ = await econ_svc.apply_task_outcome(session, t)
    await session.commit()
    assert econ.merit == -7


async def test_miss_subtracts_miss_penalty(session):
    p = await _profile(session)
    t = await _resolved_task(session, p.id, TaskStatus.MISSED, miss=12)
    econ = await econ_svc.apply_task_outcome(session, t)
    await session.commit()
    assert econ.merit == -12


async def test_consecutive_passes_apply_streak_multiplier(session):
    p = await _profile(session)
    t1 = await _resolved_task(session, p.id, TaskStatus.VERIFIED_PASS, reward=10)
    await econ_svc.apply_task_outcome(session, t1)
    await session.commit()
    t2 = await _resolved_task(session, p.id, TaskStatus.VERIFIED_PASS, reward=10)
    await econ_svc.apply_task_outcome(session, t2)
    await session.commit()
    t3 = await _resolved_task(session, p.id, TaskStatus.VERIFIED_PASS, reward=10)
    econ = await econ_svc.apply_task_outcome(session, t3)
    await session.commit()
    # 10 + round(10*1.25) + round(10*1.5) = 10 + 13 + 15 = 38
    assert econ.merit == 38


async def test_non_terminal_status_is_noop(session):
    p = await _profile(session)
    t = await _resolved_task(session, p.id, TaskStatus.PROOF_SUBMITTED, reward=10)
    econ = await econ_svc.apply_task_outcome(session, t)
    await session.commit()
    assert econ.merit == 0
