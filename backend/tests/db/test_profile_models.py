from sqlalchemy import select

from app.db.enums import GoalStatus, KinkRating
from app.db.models.profile import Goal, KinkEntry, SubProfile, Toy


async def test_persist_profile_with_children(session):
    profile = SubProfile(intensity_ceiling=70, aftercare_prefs="quiet reassurance")
    profile.kinks.append(KinkEntry(kink="bondage", rating=KinkRating.HARD_LIMIT))
    profile.toys.append(Toy(name="Wand", type="vibrator", intiface_capable=True))
    profile.goals.append(Goal(title="Daily journaling", description="write 200 words"))
    session.add(profile)
    await session.commit()

    fetched = (await session.execute(select(SubProfile))).scalar_one()
    assert fetched.intensity_ceiling == 70
    assert fetched.kinks[0].rating is KinkRating.HARD_LIMIT
    assert fetched.toys[0].intiface_capable is True
    assert fetched.goals[0].status is GoalStatus.ACTIVE  # default


async def test_kink_rating_persists_as_enum(session):
    profile = SubProfile(intensity_ceiling=50)
    profile.kinks.append(KinkEntry(kink="praise", rating=KinkRating.FAVORITE))
    session.add(profile)
    await session.commit()

    entry = (await session.execute(select(KinkEntry))).scalar_one()
    assert entry.rating is KinkRating.FAVORITE
    assert entry.kink == "praise"
