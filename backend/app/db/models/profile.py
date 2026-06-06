from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import GoalStatus, KinkRating


class SubProfile(Base):
    __tablename__ = "sub_profile"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    intensity_ceiling: Mapped[int] = mapped_column(default=50)
    aftercare_prefs: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    kinks: Mapped[list[KinkEntry]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    toys: Mapped[list[Toy]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    goals: Mapped[list[Goal]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    archetype_results: Mapped[list[ArchetypeResult]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    so_context: Mapped[SoContext | None] = relationship(
        back_populates="profile", cascade="all, delete-orphan", uselist=False
    )


class ArchetypeResult(Base):
    __tablename__ = "archetype_result"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))
    raw_answers: Mapped[dict] = mapped_column(JSONB, default=dict)
    scores: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    profile: Mapped[SubProfile] = relationship(back_populates="archetype_results")


class KinkEntry(Base):
    __tablename__ = "kink_entry"
    __table_args__ = (UniqueConstraint("profile_id", "kink", name="uq_profile_kink"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))
    kink: Mapped[str] = mapped_column(String)
    rating: Mapped[KinkRating] = mapped_column(Enum(KinkRating, name="kink_rating"))

    profile: Mapped[SubProfile] = relationship(back_populates="kinks")


class Toy(Base):
    __tablename__ = "toy"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    intiface_capable: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(String, default=None)

    profile: Mapped[SubProfile] = relationship(back_populates="toys")


class SoContext(Base):
    __tablename__ = "so_context"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sub_profile.id"), unique=True
    )
    description: Mapped[str] = mapped_column(String, default="")
    values: Mapped[str | None] = mapped_column(String, default=None)
    dynamic: Mapped[str | None] = mapped_column(String, default=None)

    profile: Mapped[SubProfile] = relationship(back_populates="so_context")


class Goal(Base):
    __tablename__ = "goal"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, default="")
    status: Mapped[GoalStatus] = mapped_column(
        Enum(GoalStatus, name="goal_status"), default=GoalStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    profile: Mapped[SubProfile] = relationship(back_populates="goals")
