from datetime import datetime, timedelta, timezone

from app.db.enums import ProofRequirement, SupervisionMode, TaskStatus
from app.db.models.punishment import Punishment
from app.loop import service as loop_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from app.supervision import service as sup_svc
from sqlalchemy import func, select


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_vacation_freezes_miss_sweep(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.VACATION)
    task = await loop_svc.assign_task(
        session, p.id, description="drill", proof_requirement=ProofRequirement.HONOR,
        deadline=datetime.now(timezone.utc) - timedelta(hours=1), merit_miss_penalty=5,
    )
    await loop_svc.sweep_missed(session, p.id)
    assert task.status is TaskStatus.ASSIGNED  # not missed — frozen


async def test_vacation_blocks_punishment_issuance_on_fail(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.VACATION)
    task = await loop_svc.assign_task(
        session, p.id, description="drill", proof_requirement=ProofRequirement.HONOR,
    )
    task.status = TaskStatus.VERIFIED_FAIL
    await session.flush()
    await loop_svc.apply_terminal_discipline(session, task)
    count = (await session.execute(
        select(func.count()).select_from(Punishment).where(Punishment.profile_id == p.id)
    )).scalar_one()
    assert count == 0  # no debt accrual under vacation
