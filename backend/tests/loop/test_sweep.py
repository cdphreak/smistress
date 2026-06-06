from datetime import datetime, timedelta, timezone

from app.db.enums import ProofRequirement, TaskStatus
from app.economy import service as econ_svc
from app.loop import service as loop_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_sweep_marks_overdue_unstarted_tasks_missed(session):
    p = await _profile(session)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    overdue = await loop_svc.assign_task(
        session, p.id, description="overdue", proof_requirement=ProofRequirement.HONOR,
        deadline=past,
    )
    on_time = await loop_svc.assign_task(
        session, p.id, description="future", proof_requirement=ProofRequirement.HONOR,
        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    await session.commit()

    count = await loop_svc.sweep_missed(session)
    await session.commit()

    assert count == 1
    refreshed = await session.get(type(overdue), overdue.id)
    assert refreshed.status is TaskStatus.MISSED
    still = await session.get(type(on_time), on_time.id)
    assert still.status is TaskStatus.ASSIGNED


async def test_sweep_ignores_tasks_awaiting_verification(session):
    p = await _profile(session)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    task = await loop_svc.assign_task(
        session, p.id, description="submitted late but submitted",
        proof_requirement=ProofRequirement.HONOR,
        deadline=past,
    )
    await session.commit()
    await loop_svc.submit_proof(session, task.id, report="done")  # now proof_submitted
    await session.commit()

    count = await loop_svc.sweep_missed(session)
    await session.commit()
    assert count == 0  # proof_submitted is not "missed"


async def test_sweep_applies_miss_penalty(session):
    from datetime import datetime, timedelta, timezone
    p = await _profile(session)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    await loop_svc.assign_task(
        session, p.id, description="overdue", proof_requirement=ProofRequirement.HONOR,
        deadline=past, merit_miss_penalty=8,
    )
    await session.commit()
    await loop_svc.sweep_missed(session)
    await session.commit()

    econ = await econ_svc.get_economy(session, p.id)
    assert econ.merit == -8
