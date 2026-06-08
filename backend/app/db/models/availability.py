from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LlmHeartbeat(Base):
    """Single-row, system-wide record of the home-box LLM's last heartbeat
    (Addendum B2). The app is single-user, so availability is global, not
    per-profile. ``last_heartbeat_at`` is None until the agent first reports."""

    __tablename__ = "llm_availability"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    source: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
