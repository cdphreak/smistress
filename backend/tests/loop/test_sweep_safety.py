from datetime import datetime, timedelta, timezone

from app.db.enums import ProofRequirement
from app.economy import service as econ_svc
from app.loop import service as loop_svc
from app.safety import service as safety_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _overdue_task(session, profile_id):
    return await loop_svc.assign_task(
        session, profile_id,
        description="overdue chore",
        proof_requirement=ProofRequirement.HONOR,
        deadline=datetime.now(timezone.utc) - timedelta(hours=1),
        merit_miss_penalty=10,
    )


async def test_sweep_skips_profile_on_hiatus(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    task = await _overdue_task(session, p.id)
    await safety_svc.set_hiatus(session, p.id, True)
    before = (await econ_svc.get_economy(session, p.id)).merit

    missed = await loop_svc.sweep_missed(session, p.id)

    assert missed == 0
    from app.loop.service import _get_task
    refreshed = await _get_task(session, task.id)
    assert refreshed.status.value == "assigned"  # not missed
    assert (await econ_svc.get_economy(session, p.id)).merit == before  # no penalty


async def test_sweep_still_misses_active_profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await _overdue_task(session, p.id)
    missed = await loop_svc.sweep_missed(session, p.id)
    assert missed == 1
