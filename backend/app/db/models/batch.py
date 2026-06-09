from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import ProofRequirement
from app.db.models.profile import SubProfile


class TaskPoolItem(Base):
    """A pre-generated, undropped task template (Addendum B4 task pool).

    The assignment drone draws one and materializes it into a real Task while
    offline — no LLM present. Carries merit stakes only; debt stakes (M4) and
    the intensity/discreetness profile (B6/M5) are added by later milestones.
    """

    __tablename__ = "task_pool_item"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))

    description: Mapped[str] = mapped_column(String)
    proof_requirement: Mapped[ProofRequirement] = mapped_column(
        Enum(ProofRequirement, name="proof_requirement")
    )
    difficulty: Mapped[str] = mapped_column(String, default="standard")

    merit_reward: Mapped[int] = mapped_column(default=0)
    merit_fail_penalty: Mapped[int] = mapped_column(default=0)
    merit_miss_penalty: Mapped[int] = mapped_column(default=0)

    consumed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    profile: Mapped[SubProfile] = relationship()


class DroneLine(Base):
    """A pre-generated in-persona drone line (Addendum B4 line bank).

    Drawn by event x merit band x time-of-day so offline lines vary day to day
    without an LLM. ``text`` may contain a ``{task}`` placeholder (task_drop).
    """

    __tablename__ = "drone_line"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))

    # "assignment" | "reminder" — informational only; the drone engine routes
    # lines by `event`, not by unit (pick_line does not filter on unit).
    unit: Mapped[str] = mapped_column(String)
    event: Mapped[str] = mapped_column(String)  # "task_drop" | "no_task" | "batch_window"
    merit_band: Mapped[str] = mapped_column(String, default="any")  # low|mid|high|any
    time_of_day: Mapped[str] = mapped_column(String, default="any")  # morning|day|evening|night|any
    text: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    profile: Mapped[SubProfile] = relationship()
