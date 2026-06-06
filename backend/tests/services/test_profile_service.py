import pytest
from sqlalchemy import select

from app.db.enums import KinkRating
from app.db.models.character import CharacterModel
from app.db.models.economy import EconomyState
from app.db.models.profile import KinkEntry
from app.schemas.onboarding import KinkItem, ProfileCreate
from app.services import profile as svc


async def test_create_profile_seeds_character_and_economy(session):
    profile = await svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True, intensity_ceiling=70)
    )
    await session.commit()

    assert profile.intensity_ceiling == 70
    char = (await session.execute(select(CharacterModel))).scalar_one()
    assert char.profile_id == profile.id
    assert char.honorific == "Headmistress"  # default persona
    econ = (await session.execute(select(EconomyState))).scalar_one()
    assert econ.profile_id == profile.id
    assert econ.merit == 0


async def test_replace_kinks_is_idempotent(session):
    profile = await svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await svc.replace_kinks(session, profile.id, [
        KinkItem(kink="bondage", rating=KinkRating.FAVORITE),
        KinkItem(kink="humiliation", rating=KinkRating.SOFT_LIMIT),
    ])
    await session.commit()
    # replacing again with one entry leaves exactly one row
    await svc.replace_kinks(session, profile.id, [
        KinkItem(kink="spanking", rating=KinkRating.LIKE),
    ])
    await session.commit()

    rows = (await session.execute(
        select(KinkEntry).where(KinkEntry.profile_id == profile.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].kink == "spanking"


async def test_get_profile_or_404_raises_for_missing(session):
    import uuid
    with pytest.raises(svc.ProfileNotFound):
        await svc.get_profile(session, uuid.uuid4())
