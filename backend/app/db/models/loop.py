from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.task import Task


class Proof(Base):
    """A single proof submission for a task and its verification verdict (spec 6).

    verdict is a plain string: pending | pass | fail | re_proof (no PG enum).
    """

    __tablename__ = "proof"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task.id"))
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))
    content: Mapped[str] = mapped_column(Text, default="")  # honor report / timer note

    verdict: Mapped[str] = mapped_column(String, default="pending")
    confidence: Mapped[int | None] = mapped_column(default=None)  # 0-100, None when n/a
    reasoning: Mapped[str] = mapped_column(Text, default="")
    issues: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    task: Mapped[Task] = relationship()


class TaskTimer(Base):
    """Server-side timer for a timer-proof task (deterministic, hard to fudge; spec 6)."""

    __tablename__ = "task_timer"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task.id"), unique=True)
    required_seconds: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    task: Mapped[Task] = relationship()
