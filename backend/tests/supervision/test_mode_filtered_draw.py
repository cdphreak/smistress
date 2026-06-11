from datetime import datetime, timedelta, timezone

from app.batch import service as batch_svc
from app.db.enums import Discreetness, ProofRequirement, SupervisionMode
from app.db.models.batch import TaskPoolItem
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from app.supervision import service as sup_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


def _pool_task(profile_id, **kw):
    kw.setdefault("description", "drill")
    kw.setdefault("proof_requirement", ProofRequirement.HONOR)
    return TaskPoolItem(profile_id=profile_id, **kw)


async def test_discreet_mode_skips_overt_picks_discreet(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.DISCREET)
    session.add(_pool_task(p.id, description="loud", discreetness=Discreetness.OVERT))
    session.add(_pool_task(p.id, description="quiet", discreetness=Discreetness.DISCREET))
    await session.flush()
    task = await batch_svc.draw_and_assign(session, p.id)
    assert task is not None
    assert task.description == "quiet"
    assert task.deadline is None  # discreet mode is not task mode -> no grace deadline


async def test_no_allowed_task_returns_none(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.HOMEOFFICE)
    session.add(_pool_task(p.id, discreetness=Discreetness.DISCREET))  # not silent
    await session.flush()
    assert await batch_svc.draw_and_assign(session, p.id) is None


async def test_intensity_ceiling_skips_too_intense(session):
    p = await _profile(session)  # default intensity_ceiling 50
    session.add(_pool_task(p.id, description="brutal", intensity=80))
    session.add(_pool_task(p.id, description="gentle", intensity=10))
    await session.flush()
    task = await batch_svc.draw_and_assign(session, p.id)
    assert task is not None and task.description == "gentle"


async def test_task_mode_stamps_grace_deadline(session):
    p = await _profile(session)
    await sup_svc.set_mode(session, p.id, SupervisionMode.TASK)
    session.add(_pool_task(p.id))
    await session.flush()
    now = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)
    task = await batch_svc.draw_and_assign(session, p.id, now=now)
    assert task is not None
    assert task.deadline is not None
    assert task.deadline == now + timedelta(hours=24)  # task_mode_grace_hours default


async def test_task_carries_pool_profile(session):
    p = await _profile(session)
    toy_id = "00000000-0000-0000-0000-000000000001"
    session.add(_pool_task(
        p.id, intensity=20, discreetness=Discreetness.SILENT, required_toy_ids=[toy_id],
    ))
    await session.flush()
    task = await batch_svc.draw_and_assign(session, p.id)
    assert task is not None
    assert task.intensity == 20
    assert task.discreetness is Discreetness.SILENT
    assert task.required_toy_ids == [toy_id]
    assert task.deadline is None  # FULL mode does not stamp a deadline
