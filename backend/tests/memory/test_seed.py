from sqlalchemy import select

from app.db.enums import KinkRating
from app.db.models.memory import MemoryEpisode
from app.memory import service as mem_svc
from app.schemas.onboarding import KinkItem, ProfileCreate
from app.services import profile as profile_svc


async def test_seed_profile_episode_enqueues_summary(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await profile_svc.replace_kinks(session, p.id, [
        KinkItem(kink="blood", rating=KinkRating.HARD_LIMIT),
    ])
    await session.commit()

    ep = await mem_svc.seed_profile_episode(session, p.id)
    await session.commit()

    assert ep.status == "pending"
    assert ep.source == "text"
    assert "blood" in ep.body            # the summary carries the authoritative state
    row = (await session.execute(select(MemoryEpisode))).scalar_one()
    assert row.id == ep.id
