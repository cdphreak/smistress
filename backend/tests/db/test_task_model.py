from sqlalchemy import select

from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.profile import SubProfile
from app.db.models.task import Task


async def test_task_defaults_and_stakes(session):
    profile = SubProfile(intensity_ceiling=60)
    session.add(profile)
    await session.flush()
    session.add(
        Task(
            profile_id=profile.id,
            description="Make the bed",
            proof_requirement=ProofRequirement.PHOTO,
            merit_reward=5,
            merit_fail_penalty=3,
            merit_miss_penalty=8,
        )
    )
    await session.commit()

    t = (await session.execute(select(Task))).scalar_one()
    assert t.status is TaskStatus.ASSIGNED  # default
    assert t.proof_requirement is ProofRequirement.PHOTO
    assert t.merit_miss_penalty == 8
    assert t.lesson_id is None  # forward-compat for the Class System (sub-project #2)


async def test_task_punitive_defaults_false(session):
    p = SubProfile(intensity_ceiling=50)
    session.add(p)
    await session.flush()
    t = Task(profile_id=p.id, description="x", proof_requirement=ProofRequirement.HONOR)
    session.add(t)
    await session.flush()
    assert t.punitive is False
