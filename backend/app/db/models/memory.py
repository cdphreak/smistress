from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.profile import SubProfile


class MemoryEpisode(Base):
    """Transactional outbox for Graphiti episodes (spec 3 'writes queue and retry').

    A row is written in the same transaction as the state change it records, then a
    drainer pushes it to the memory store and retries on failure. status: pending|done.
    """

    __tablename__ = "memory_episode"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))
    name: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String, default="text")  # EpisodeType value
    source_description: Mapped[str] = mapped_column(String, default="")
    reference_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String, default="pending")  # pending | done
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    profile: Mapped[SubProfile] = relationship()
