from app.db.models.character import CharacterModel
from app.persona.character_block import render_character_block


def _default_character() -> CharacterModel:
    # In-memory ORM instance; mirrors the M2 defaults (no DB needed).
    return CharacterModel(
        honorific="Headmistress",
        address_term="student",
        pronouns="she/her",
        archetype_blend={"governess": 70, "drill_instructor": 30},
        warmth=30,
        strictness=80,
        sadism=30,
        formality=80,
        verbosity=50,
        crudeness=20,
        wit=75,
    )


def test_block_includes_identity_and_address():
    block = render_character_block(_default_character())
    assert "Headmistress" in block
    assert "student" in block
    assert "she/her" in block


def test_block_describes_archetype_blend_in_weight_order():
    block = render_character_block(_default_character())
    # Governess (70) named before Drill Instructor (30).
    assert block.index("Governess") < block.index("Drill Instructor")
    assert "70" in block and "30" in block


def test_block_translates_dials_to_descriptors():
    block = render_character_block(_default_character()).lower()
    # high strictness/wit/formality -> "high"; low crudeness -> "low"; warmth moderate-low.
    assert "strictness" in block
    assert "high" in block
    assert "low" in block


def test_signature_flavor_included_when_present():
    char = _default_character()
    char.signature_flavor = "Quotes Latin proverbs when displeased."
    block = render_character_block(char)
    assert "Latin proverbs" in block


def test_named_character_uses_name():
    char = _default_character()
    char.name = "Vesper"
    assert "Vesper" in render_character_block(char)
