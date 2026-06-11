from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import Discreetness, ProofRequirement, TaskStatus
from app.db.models.profile import SubProfile


class Task(Base):
    """A single assigned task (spec 6). lesson_id is nullable for the future Class System."""

    __tablename__ = "task"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(default=None)

    description: Mapped[str] = mapped_column(String)
    proof_requirement: Mapped[ProofRequirement] = mapped_column(
        Enum(ProofRequirement, name="proof_requirement")
    )
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    merit_reward: Mapped[int] = mapped_column(default=0)
    merit_fail_penalty: Mapped[int] = mapped_column(default=0)
    merit_miss_penalty: Mapped[int] = mapped_column(default=0)

    intensity: Mapped[int] = mapped_column(default=0)  # 0-100, clamped by the ceiling
    discreetness: Mapped[Discreetness] = mapped_column(
        Enum(Discreetness, name="discreetness"), default=Discreetness.OVERT
    )
    required_toy_ids: Mapped[list] = mapped_column(JSONB, default=list)  # list[str] toy UUIDs

    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"), default=TaskStatus.ASSIGNED
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    profile: Mapped[SubProfile] = relationship()
