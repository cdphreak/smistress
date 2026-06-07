import uuid

import pytest
from sqlalchemy import func, select

from app.db.enums import KinkRating, ProofRequirement
from app.db.models.economy import EconomyState
from app.db.models.profile import KinkEntry, SubProfile
from app.db.models.safety import SafetyState
from app.db.models.task import Task
from app.loop import service as loop_svc
from app.schemas.onboarding import GoalIn, KinkItem, ProfileCreate
from app.services import profile as profile_svc


async def test_delete_profile_removes_all_related_rows(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await profile_svc.replace_kinks(session, p.id, [KinkItem(kink="blood", rating=KinkRating.HARD_LIMIT)])
    await profile_svc.add_goal(session, p.id, GoalIn(title="g"))
    await loop_svc.assign_task(
        session, p.id, description="t", proof_requirement=ProofRequirement.HONOR,
    )
    await session.commit()

    await profile_svc.delete_profile(session, p.id)
    await session.commit()

    assert await session.get(SubProfile, p.id) is None
    for model in (EconomyState, SafetyState, KinkEntry, Task):
        count = (await session.execute(
            select(func.count()).select_from(model).where(model.profile_id == p.id)
        )).scalar_one()
        assert count == 0


async def test_delete_profile_unknown_raises(session):
    with pytest.raises(profile_svc.ProfileNotFound):
        await profile_svc.delete_profile(session, uuid.uuid4())
