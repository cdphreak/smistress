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


async def test_reminder_notice_for_active_denial_timer(session):
    from app.economy import service as econ_svc

    p = await _profile(session)
    ends = datetime.now(timezone.utc) + timedelta(hours=8)
    await econ_svc.set_denial_timer(session, p.id, reason="overnight discipline", ends_at=ends)
    notices = await drone_svc.standing_orders(session, p.id)
    reminders = [n for n in notices if n.unit == "reminder"]
    assert any("denial" in n.line.lower() for n in reminders)
    assert any("overnight discipline" in n.line for n in reminders)


async def test_reminder_notice_for_passed_deadline(session):
    p = await _profile(session)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    session.add(
        Task(
            profile_id=p.id,
            description="Late drill",
            proof_requirement=ProofRequirement.HONOR,
            status=TaskStatus.ASSIGNED,
            deadline=past,
        )
    )
    await session.flush()
    notices = await drone_svc.standing_orders(session, p.id)
    reminders = [n for n in notices if n.unit == "reminder"]
    assert any("deadline has passed" in n.line.lower() for n in reminders)


async def test_reminder_notice_for_deadline_due_soon(session):
    p = await _profile(session)
    soon = datetime.now(timezone.utc) + timedelta(hours=3)
    session.add(
        Task(
            profile_id=p.id,
            description="Soon drill",
            proof_requirement=ProofRequirement.HONOR,
            status=TaskStatus.ASSIGNED,
            deadline=soon,
        )
    )
    await session.flush()
    notices = await drone_svc.standing_orders(session, p.id)
    reminders = [n for n in notices if n.unit == "reminder"]
    assert any("due within the day" in n.line.lower() for n in reminders)


async def test_no_state_reminder_when_no_timers_or_deadline(session):
    p = await _profile(session)
    session.add(
        Task(
            profile_id=p.id,
            description="No deadline drill",
            proof_requirement=ProofRequirement.HONOR,
            status=TaskStatus.ASSIGNED,
        )
    )
    await session.flush()
    notices = await drone_svc.standing_orders(session, p.id)
    reminders = [n for n in notices if n.unit == "reminder"]
    # denial/deadline reminders are absent; only the (empty-pool) batch-window prompt may remain
    assert all("denial" not in n.line.lower() for n in reminders)
    assert all("deadline" not in n.line.lower() for n in reminders)


async def test_bank_line_used_for_task_drop_when_available(session):
    from app.db.models.batch import DroneLine

    p = await _profile(session)
    session.add(
        Task(
            profile_id=p.id, description="Posture drill",
            proof_requirement=ProofRequirement.HONOR, status=TaskStatus.ASSIGNED,
        )
    )
    session.add(DroneLine(
        profile_id=p.id, unit="assignment", event="task_drop",
        merit_band="any", time_of_day="any", text="DRONE-7 logs your charge: {task}.",
    ))
    await session.flush()
    notices = await drone_svc.standing_orders(session, p.id)
    assignment = [n for n in notices if n.unit == "assignment"][0]
    assert assignment.line == "DRONE-7 logs your charge: Posture drill."


async def test_assignment_unit_drops_a_pooled_task_when_none_active(session):
    from app.db.models.batch import TaskPoolItem
    from app.db.models.task import Task as TaskModel
    from sqlalchemy import select

    p = await _profile(session)
    session.add(TaskPoolItem(
        profile_id=p.id, description="Drawn drill", proof_requirement=ProofRequirement.HONOR,
        merit_reward=5,
    ))
    await session.flush()
    notices = await drone_svc.standing_orders(session, p.id)
    assignment = [n for n in notices if n.unit == "assignment"][0]
    assert "Drawn drill" in assignment.line
    task = (await session.execute(select(TaskModel))).scalar_one()
    assert task.status is TaskStatus.ASSIGNED


async def test_batch_window_reminder_when_pool_low(session):
    p = await _profile(session)
    notices = await drone_svc.standing_orders(session, p.id)
    reminders = [n for n in notices if n.unit == "reminder"]
    assert any("batch window" in n.line.lower() for n in reminders)
