from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.enums import ProofRequirement, PunishmentStatus, PunishmentType, TaskStatus
from app.db.models.punishment import Punishment
from app.db.models.task import Task
from app.economy import service as econ_svc
from app.memory import service as mem_svc

_settings = Settings()


async def issue_punishment(
    session: AsyncSession,
    profile_id: uuid.UUID,
    *,
    type: PunishmentType,
    severity: int,
    reason: str = "",
    now: datetime | None = None,
) -> Punishment:
    """The discipline unit issues a consequence (Addendum B7): records a ledger
    entry, accrues debt, and enacts the type's effect. Caller commits."""
    now = now or datetime.now(timezone.utc)
    debt_amount = _settings.debt_by_severity[severity]

    punishment = Punishment(
        profile_id=profile_id, type=type, severity=severity, reason=reason,
        debt_amount=debt_amount, status=PunishmentStatus.ISSUED,
    )
    session.add(punishment)
    await session.flush()
    await econ_svc.adjust_debt(session, profile_id, debt_amount)

    if type is PunishmentType.CHASTITY_EXTENSION:
        hours = _settings.chastity_hours_by_severity[severity]
        await econ_svc.extend_chastity(session, profile_id, hours=hours, now=now)
    elif type is PunishmentType.TOKEN_CONFISCATION:
        amount = _settings.confiscation_by_severity[severity]
        econ = await econ_svc.get_economy(session, profile_id)
        await econ_svc.spend_tokens(session, profile_id, min(amount, econ.tokens))
    elif type is PunishmentType.PENANCE_TASK:
        task = Task(
            profile_id=profile_id,
            description=reason or "Serve your penance.",
            proof_requirement=ProofRequirement.HONOR,
            status=TaskStatus.ASSIGNED,
        )
        session.add(task)
        await session.flush()
        punishment.penance_task_id = task.id
        await mem_svc.enqueue_episode(
            session, profile_id, name="penance issued",
            body=f"Penance assigned: {task.description}.",
            source="text", source_description="discipline", reference_time=now,
        )

    await session.flush()
    return punishment


async def settle_penance(session: AsyncSession, task: Task) -> Punishment | None:
    """Settle the penance linked to a just-passed Task (Addendum B7): clear its
    debt and grant a small merit recovery for an honest serve. Returns None if the
    task is not a penance or is already settled. Caller commits."""
    punishment = (await session.execute(
        select(Punishment).where(
            Punishment.penance_task_id == task.id,
            Punishment.status == PunishmentStatus.ISSUED,
        )
    )).scalar_one_or_none()
    if punishment is None:
        return None
    punishment.status = PunishmentStatus.SERVED
    punishment.resolved_at = datetime.now(timezone.utc)
    await econ_svc.adjust_debt(session, task.profile_id, -punishment.debt_amount)
    await econ_svc.adjust_merit(session, task.profile_id, _settings.penance_merit_recovery)
    await session.flush()
    return punishment
