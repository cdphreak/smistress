from sqlalchemy import select

from app.db.enums import ProofRequirement
from app.db.models.loop import Proof, TaskTimer
from app.db.models.profile import SubProfile
from app.db.models.task import Task


async def _task(session) -> Task:
    p = SubProfile(intensity_ceiling=50)
    session.add(p)
    await session.flush()
    t = Task(profile_id=p.id, description="make the bed", proof_requirement=ProofRequirement.HONOR)
    session.add(t)
    await session.flush()
    return t


async def test_proof_defaults(session):
    t = await _task(session)
    session.add(Proof(task_id=t.id, profile_id=t.profile_id, content="I did it."))
    await session.commit()
    pr = (await session.execute(select(Proof))).scalar_one()
    assert pr.verdict == "pending"
    assert pr.confidence is None
    assert pr.reasoning == ""
    assert pr.issues == []


async def test_task_timer_defaults(session):
    t = await _task(session)
    session.add(TaskTimer(task_id=t.id, required_seconds=600))
    await session.commit()
    tt = (await session.execute(select(TaskTimer))).scalar_one()
    assert tt.required_seconds == 600
    assert tt.started_at is None
    assert tt.stopped_at is None
