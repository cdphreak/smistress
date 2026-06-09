from app.batch import service as batch_svc
from app.db.enums import ProofRequirement
from app.db.models.batch import DroneLine, TaskPoolItem
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_pool_status_empty_is_low(session):
    p = await _profile(session)
    status = await batch_svc.pool_status(session, p.id)
    assert status.task_pool == 0
    assert status.line_bank == 0
    assert status.task_pool_low is True
    assert status.line_bank_low is True
    assert status.punishment_pool == 0
    assert status.punishment_pool_low is True


async def test_pool_status_counts_only_unconsumed_tasks(session):
    p = await _profile(session)
    session.add(TaskPoolItem(
        profile_id=p.id, description="a", proof_requirement=ProofRequirement.HONOR
    ))
    session.add(TaskPoolItem(
        profile_id=p.id, description="b", proof_requirement=ProofRequirement.HONOR, consumed=True
    ))
    session.add(DroneLine(profile_id=p.id, unit="assignment", event="task_drop", text="x"))
    await session.flush()
    status = await batch_svc.pool_status(session, p.id)
    assert status.task_pool == 1  # consumed item excluded
    assert status.line_bank == 1
