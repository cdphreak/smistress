from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.profile import SubProfile


class EconomyState(Base):
    """One per profile. The three quantities (Addendum B7): merit (standing),
    tokens (reward purse), and debt (owed penance). Merit also drives disposition."""

    __tablename__ = "economy_state"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sub_profile.id"), unique=True
    )
    merit: Mapped[int] = mapped_column(default=0)
    rank: Mapped[str] = mapped_column(String, default="novice")
    tokens: Mapped[int] = mapped_column(default=0)
    debt: Mapped[int] = mapped_column(default=0)  # owed penance; never negative

    profile: Mapped[SubProfile] = relationship()


class ChastityTimer(Base):
    """A single per-profile chastity countdown (Addendum B7, generalizing the old
    denial timer). ``ends_at`` is the scheduled release; None means not locked.
    Locked iff ends_at is set and in the future; extensions push it out; only she
    lifts it early (serving penance never shortens it)."""

    __tablename__ = "chastity_timer"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sub_profile.id"), unique=True
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    note: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    profile: Mapped[SubProfile] = relationship()
