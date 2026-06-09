from datetime import datetime, timedelta, timezone

from app.db.enums import ProofRequirement, PunishmentStatus, PunishmentType, TaskStatus
from app.db.models.punishment import Punishment
from app.db.models.task import Task
from app.discipline import service as disc_svc
from app.economy import service as econ_svc
from app.loop import service as loop_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from sqlalchemy import func, select


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_missed_task_issues_a_punishment(session):
    p = await _profile(session)
    task = await loop_svc.assign_task(
        session, p.id, description="drill", proof_requirement=ProofRequirement.HONOR,
        deadline=datetime.now(timezone.utc) - timedelta(hours=1), merit_miss_penalty=5,
    )
    await loop_svc.sweep_missed(session, p.id)
    assert task.status is TaskStatus.MISSED
    count = (await session.execute(
        select(func.count()).select_from(Punishment).where(Punishment.profile_id == p.id)
    )).scalar_one()
    assert count == 1
    assert (await econ_svc.get_economy(session, p.id)).debt > 0


async def test_passing_a_penance_task_settles_it(session):
    p = await _profile(session)
    pun = await disc_svc.issue_punishment(
        session, p.id, type=PunishmentType.PENANCE_TASK, severity=1, reason="penance",
    )
    task = await session.get(Task, pun.penance_task_id)
    task.status = TaskStatus.VERIFIED_PASS
    await session.flush()
    await loop_svc.apply_terminal_discipline(session, task)
    settled = (await session.execute(
        select(Punishment).where(Punishment.id == pun.id)
    )).scalar_one()
    assert settled.status is PunishmentStatus.SERVED
