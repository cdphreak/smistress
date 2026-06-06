from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.profile import SubProfile


class EconomyState(Base):
    """One per profile. Merit is the core currency (also drives disposition, spec 5/7)."""

    __tablename__ = "economy_state"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sub_profile.id"), unique=True
    )
    merit: Mapped[int] = mapped_column(default=0)
    rank: Mapped[str] = mapped_column(String, default="novice")
    tokens: Mapped[int] = mapped_column(default=0)

    profile: Mapped[SubProfile] = relationship()


class DenialTimer(Base):
    """In-app denial countdown (spec 7). Phase 2 also gates Intiface device pleasure."""

    __tablename__ = "denial_timer"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))
    reason: Mapped[str] = mapped_column(String, default="")
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    profile: Mapped[SubProfile] = relationship()
