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


async def test_task_pool_item_round_trip(session):
    p = await _profile(session)
    item = TaskPoolItem(
        profile_id=p.id,
        description="Ten slow squats, posture held.",
        proof_requirement=ProofRequirement.HONOR,
        difficulty="standard",
        merit_reward=8,
        merit_miss_penalty=4,
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)
    assert item.consumed is False
    assert item.proof_requirement is ProofRequirement.HONOR


async def test_drone_line_round_trip(session):
    p = await _profile(session)
    line = DroneLine(
        profile_id=p.id,
        unit="assignment",
        event="task_drop",
        merit_band="mid",
        time_of_day="morning",
        text="Mistress has set you: {task}. Report when complete.",
    )
    session.add(line)
    await session.flush()
    await session.refresh(line)
    assert "{task}" in line.text
    assert line.merit_band == "mid"
