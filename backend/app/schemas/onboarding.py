from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.enums import GoalStatus, KinkRating, ToyType


def _dial() -> int | None:
    """0-100 voice dial, optional for partial updates."""
    return Field(default=None, ge=0, le=100)  # type: ignore[return-value]


# ---- create / read profile ------------------------------------------------
class ProfileCreate(BaseModel):
    is_adult: bool
    consent_acknowledged: bool
    intensity_ceiling: int = Field(default=50, ge=0, le=100)
    aftercare_prefs: str | None = None


class ProfileCreated(BaseModel):
    id: UUID
    intensity_ceiling: int


# ---- preferences ----------------------------------------------------------
class PreferencesIn(BaseModel):
    intensity_ceiling: int = Field(default=50, ge=0, le=100)
    aftercare_prefs: str | None = None


class PreferencesOut(BaseModel):
    intensity_ceiling: int
    aftercare_prefs: str | None
    model_config = ConfigDict(from_attributes=True)


# ---- archetype ------------------------------------------------------------
class ArchetypeSubmission(BaseModel):
    # statement id -> agreement 0..4
    answers: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @field_validator("answers")
    @classmethod
    def answers_in_range(cls, v: dict[str, int]) -> dict[str, int]:
        for key, val in v.items():
            if not (0 <= val <= 4):
                raise ValueError(f"answer '{key}' must be between 0 and 4, got {val}")
        return v


class ArchetypeResultOut(BaseModel):
    scores: dict[str, int]


# ---- kink sheet -----------------------------------------------------------
class KinkItem(BaseModel):
    kink: str
    rating: KinkRating


class KinkSheetIn(BaseModel):
    entries: list[KinkItem]


# ---- toys -----------------------------------------------------------------
class ToyIn(BaseModel):
    name: str
    type: ToyType
    intiface_capable: bool = False
    notes: str | None = None
    noise: bool = False
    visibility: bool = False
    discreet_capable: bool = False


class ToyOut(ToyIn):
    id: UUID
    model_config = ConfigDict(from_attributes=True)


# ---- goals ----------------------------------------------------------------
class GoalIn(BaseModel):
    title: str
    description: str = ""


class GoalOut(BaseModel):
    id: UUID
    title: str
    description: str
    status: GoalStatus
    model_config = ConfigDict(from_attributes=True)


# ---- SO context -----------------------------------------------------------
class SoContextIn(BaseModel):
    description: str = ""
    values: str | None = None
    dynamic: str | None = None


# ---- character model ------------------------------------------------------
class CharacterUpdate(BaseModel):
    """Partial update — only provided fields change."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    honorific: str | None = None
    address_term: str | None = None
    pronouns: str | None = None
    archetype_blend: dict[str, int] | None = None
    warmth: int | None = _dial()
    strictness: int | None = _dial()
    sadism: int | None = _dial()
    formality: int | None = _dial()
    verbosity: int | None = _dial()
    crudeness: int | None = _dial()
    wit: int | None = _dial()
    signature_flavor: str | None = None

    @field_validator("archetype_blend")
    @classmethod
    def _blend_values_in_range(cls, v: dict[str, int] | None) -> dict[str, int] | None:
        if v is not None:
            for key, weight in v.items():
                if not (0 <= weight <= 100):
                    raise ValueError(f"archetype weight for {key!r} must be 0-100")
        return v


class CharacterOut(BaseModel):
    name: str | None
    honorific: str
    address_term: str
    pronouns: str
    archetype_blend: dict[str, int]
    warmth: int
    strictness: int
    sadism: int
    formality: int
    verbosity: int
    crudeness: int
    wit: int
    signature_flavor: str | None
    model_config = ConfigDict(from_attributes=True)


# ---- assembled profile read ----------------------------------------------
class KinkOut(BaseModel):
    kink: str
    rating: KinkRating
    model_config = ConfigDict(from_attributes=True)


class ProfileRead(BaseModel):
    id: UUID
    intensity_ceiling: int
    aftercare_prefs: str | None
    archetype_scores: dict[str, int]
    kinks: list[KinkOut]
    toys: list[ToyOut]
    goals: list[GoalOut]
    so_context: SoContextIn | None
    character: CharacterOut
