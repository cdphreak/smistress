from datetime import datetime, timedelta, timezone

from app.drones import service as drone_svc
from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.task import Task
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_assignment_notice_when_no_active_task(session):
    p = await _profile(session)
    notices = await drone_svc.standing_orders(session, p.id)
    assert notices[0].unit == "assignment"
    assert "no standing assignment" in notices[0].line.lower()


async def test_assignment_notice_surfaces_active_task(session):
    p = await _profile(session)
    session.add(
        Task(
            profile_id=p.id,
            description="Posture drill",
            proof_requirement=ProofRequirement.HONOR,
            status=TaskStatus.ASSIGNED,
        )
    )
    await session.flush()
    notices = await drone_svc.standing_orders(session, p.id)
    assignment = [n for n in notices if n.unit == "assignment"]
    assert len(assignment) == 1
    assert "Posture drill" in assignment[0].line
    assert "mistress has assigned" in assignment[0].line.lower()


async def test_standing_orders_raises_for_unknown_profile(session):
    import uuid

    import pytest

    with pytest.raises(profile_svc.ProfileNotFound):
        await drone_svc.standing_orders(session, uuid.uuid4())
