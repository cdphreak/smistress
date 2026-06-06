import pytest
from pydantic import ValidationError

from app.db.enums import KinkRating
from app.schemas.onboarding import (
    ArchetypeSubmission,
    CharacterUpdate,
    KinkItem,
    KinkSheetIn,
    ProfileCreate,
)


def test_profile_create_defaults_and_bounds():
    p = ProfileCreate(is_adult=True, consent_acknowledged=True)
    assert p.intensity_ceiling == 50
    with pytest.raises(ValidationError):
        ProfileCreate(is_adult=True, consent_acknowledged=True, intensity_ceiling=101)


def test_archetype_submission_rejects_out_of_range_answer():
    ArchetypeSubmission(answers={"q1": 4})  # ok
    with pytest.raises(ValidationError):
        ArchetypeSubmission(answers={"q1": 5})


def test_kink_item_uses_enum():
    item = KinkItem(kink="bondage", rating=KinkRating.FAVORITE)
    assert item.rating is KinkRating.FAVORITE
    sheet = KinkSheetIn(entries=[item])
    assert len(sheet.entries) == 1


def test_character_update_dials_bounded_and_optional():
    c = CharacterUpdate(strictness=90)
    assert c.strictness == 90
    assert c.warmth is None  # unset fields stay None (partial update)
    with pytest.raises(ValidationError):
        CharacterUpdate(sadism=200)
