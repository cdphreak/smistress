from app.config import Settings
from app.db.enums import PunishmentStatus, PunishmentType


def test_punishment_enums_have_expected_members():
    assert {t.value for t in PunishmentType} == {
        "penance_task", "chastity_extension", "token_confiscation"
    }
    assert {s.value for s in PunishmentStatus} == {
        "issued", "served", "bought_down", "expired"
    }


def test_severity_maps_cover_1_to_3():
    s = Settings()
    for sev in (1, 2, 3):
        assert sev in s.debt_by_severity
        assert sev in s.chastity_hours_by_severity
        assert sev in s.confiscation_by_severity
    assert s.buydown_tokens_per_debt >= 1
    assert s.penance_merit_recovery >= 0


from datetime import datetime, timezone

from app.db.enums import ProofRequirement, PunishmentStatus, PunishmentType, TaskStatus
from app.db.models.task import Task
from app.discipline import service as disc_svc
from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from sqlalchemy import select


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_issue_chastity_extension_adds_debt_and_extends(session):
    p = await _profile(session)
    now = datetime.now(timezone.utc)
    pun = await disc_svc.issue_punishment(
        session, p.id, type=PunishmentType.CHASTITY_EXTENSION, severity=2,
        reason="missed drill", now=now,
    )
    assert pun.debt_amount == 15
    assert (await econ_svc.get_economy(session, p.id)).debt == 15
    status = await econ_svc.chastity_status(session, p.id, now=now)
    assert status.locked is True


async def test_issue_token_confiscation_removes_tokens(session):
    p = await _profile(session)
    await econ_svc.grant_tokens(session, p.id, 100)
    await disc_svc.issue_punishment(
        session, p.id, type=PunishmentType.TOKEN_CONFISCATION, severity=3, reason="fail",
    )
    econ = await econ_svc.get_economy(session, p.id)
    assert econ.tokens == 60
    assert econ.debt == 40


async def test_issue_penance_task_creates_linked_task(session):
    p = await _profile(session)
    pun = await disc_svc.issue_punishment(
        session, p.id, type=PunishmentType.PENANCE_TASK, severity=1,
        reason="Write 20 lines: I will report on time.",
    )
    assert pun.penance_task_id is not None
    task = await session.get(Task, pun.penance_task_id)
    assert task is not None
    assert task.status is TaskStatus.ASSIGNED
    assert task.proof_requirement is ProofRequirement.HONOR


async def test_settle_penance_clears_debt_and_recovers_small_merit(session):
    p = await _profile(session)
    pun = await disc_svc.issue_punishment(
        session, p.id, type=PunishmentType.PENANCE_TASK, severity=2, reason="penance",
    )
    assert (await econ_svc.get_economy(session, p.id)).debt == 15
    merit_before = (await econ_svc.get_economy(session, p.id)).merit

    task = await session.get(Task, pun.penance_task_id)
    settled = await disc_svc.settle_penance(session, task)
    assert settled is not None
    assert settled.status is PunishmentStatus.SERVED
    assert settled.resolved_at is not None
    econ = await econ_svc.get_economy(session, p.id)
    assert econ.debt == 0
    assert econ.merit == merit_before + 3


async def test_settle_penance_is_none_for_a_non_penance_task(session):
    p = await _profile(session)
    task = Task(
        profile_id=p.id, description="ordinary", proof_requirement=ProofRequirement.HONOR,
        status=TaskStatus.VERIFIED_PASS,
    )
    session.add(task)
    await session.flush()
    assert await disc_svc.settle_penance(session, task) is None
