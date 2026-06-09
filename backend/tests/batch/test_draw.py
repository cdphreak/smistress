from app.batch import service as batch_svc
from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.batch import TaskPoolItem
from app.db.models.task import Task
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from sqlalchemy import select


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_draw_materializes_a_task_and_consumes_the_item(session):
    p = await _profile(session)
    session.add(TaskPoolItem(
        profile_id=p.id, description="Kneel and breathe, five minutes.",
        proof_requirement=ProofRequirement.TIMER, merit_reward=6, merit_miss_penalty=4,
    ))
    await session.flush()

    task = await batch_svc.draw_and_assign(session, p.id)
    assert task is not None
    assert task.description == "Kneel and breathe, five minutes."
    assert task.status is TaskStatus.ASSIGNED
    assert task.merit_reward == 6

    item = (await session.execute(select(TaskPoolItem))).scalar_one()
    assert item.consumed is True
    assert (await session.execute(select(Task))).scalar_one().id == task.id


async def test_draw_returns_none_when_pool_empty(session):
    p = await _profile(session)
    assert await batch_svc.draw_and_assign(session, p.id) is None
