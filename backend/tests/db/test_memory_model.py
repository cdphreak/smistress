from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models.memory import MemoryEpisode
from app.db.models.profile import SubProfile


async def test_memory_episode_defaults(session):
    profile = SubProfile(intensity_ceiling=50)
    session.add(profile)
    await session.flush()
    session.add(
        MemoryEpisode(
            profile_id=profile.id,
            name="seed",
            body="A profile summary.",
            source="text",
            source_description="onboarding",
            reference_time=datetime.now(timezone.utc),
        )
    )
    await session.commit()

    ep = (await session.execute(select(MemoryEpisode))).scalar_one()
    assert ep.status == "pending"      # default
    assert ep.attempts == 0
    assert ep.last_error is None
    assert ep.source == "text"
