from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.profile import SubProfile


class SafetyState(Base):
    """Deterministic per-profile safety flags (spec 9). One row per profile.

    Halt = scene paused by safeword (resume-when-ready). Hiatus = user-requested
    pause with no merit penalty. Both freeze the loop's miss-sweep.
    """

    __tablename__ = "safety_state"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sub_profile.id"), unique=True
    )
    is_halted: Mapped[bool] = mapped_column(Boolean, default=False)
    on_hiatus: Mapped[bool] = mapped_column(Boolean, default=False)
    last_safeword_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_consent_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    profile: Mapped[SubProfile] = relationship()
