from sqlalchemy import select

from app.db.models.character import CharacterModel
from app.db.models.profile import SubProfile


async def test_character_model_defaults_governess_drill_instructor(session):
    profile = SubProfile(intensity_ceiling=60)
    session.add(profile)
    await session.flush()
    session.add(CharacterModel(profile_id=profile.id))
    await session.commit()

    cm = (await session.execute(select(CharacterModel))).scalar_one()
    assert cm.honorific == "Headmistress"
    assert cm.address_term == "student"
    assert cm.archetype_blend == {"governess": 70, "drill_instructor": 30}
    assert cm.strictness == 80
    assert cm.wit == 75
    assert cm.sadism == 30


async def test_character_dials_are_configurable(session):
    profile = SubProfile(intensity_ceiling=60)
    session.add(profile)
    await session.flush()
    session.add(CharacterModel(profile_id=profile.id, sadism=90, warmth=10, name="Vesper"))
    await session.commit()

    cm = (await session.execute(select(CharacterModel))).scalar_one()
    assert cm.sadism == 90
    assert cm.warmth == 10
    assert cm.name == "Vesper"
