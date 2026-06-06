from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.profile import SubProfile


def _default_blend() -> dict:
    return {"governess": 70, "drill_instructor": 30}


class CharacterModel(Base):
    """Configurable persona (spec 5A). Dials set her center; merit/mood swing her around it."""

    __tablename__ = "character_model"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sub_profile.id"), unique=True
    )

    # Identity
    name: Mapped[str | None] = mapped_column(String, default=None)
    honorific: Mapped[str] = mapped_column(String, default="Headmistress")
    address_term: Mapped[str] = mapped_column(String, default="student")
    pronouns: Mapped[str] = mapped_column(String, default="she/her")

    # Archetype blend (weights summing to ~100)
    archetype_blend: Mapped[dict] = mapped_column(JSONB, default=_default_blend)

    # Voice dials 0-100 (Governess + Drill Instructor defaults)
    warmth: Mapped[int] = mapped_column(default=30)
    strictness: Mapped[int] = mapped_column(default=80)
    sadism: Mapped[int] = mapped_column(default=30)
    formality: Mapped[int] = mapped_column(default=80)
    verbosity: Mapped[int] = mapped_column(default=50)
    crudeness: Mapped[int] = mapped_column(default=20)
    wit: Mapped[int] = mapped_column(default=75)

    signature_flavor: Mapped[str | None] = mapped_column(String, default=None)

    profile: Mapped[SubProfile] = relationship()
