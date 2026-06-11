from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import Discreetness, PunishmentStatus, PunishmentType
from app.db.models.profile import SubProfile


class Punishment(Base):
    """A debt-ledger line item (Addendum B7). Issued on a miss/fail; adds
    ``debt_amount`` to the economy's debt balance; cleared by serving penance
    (a linked Task verified PASS) or a token buy-down. Also carries
    discreetness/required-toy columns (B6/M5b) for parity with the pool item;
    reserved for a future snapshot — the mode filter reads the pool item, not
    this ledger row, so they are not populated at issue time."""

    __tablename__ = "punishment"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))

    type: Mapped[PunishmentType] = mapped_column(Enum(PunishmentType, name="punishment_type"))
    severity: Mapped[int] = mapped_column(default=1)  # 1 (light) .. 3 (heavy)
    reason: Mapped[str] = mapped_column(String, default="")
    debt_amount: Mapped[int] = mapped_column(default=0)
    discreetness: Mapped[Discreetness] = mapped_column(
        Enum(Discreetness, name="discreetness"), default=Discreetness.OVERT
    )
    required_toy_ids: Mapped[list] = mapped_column(JSONB, default=list)  # list[str] toy UUIDs
    status: Mapped[PunishmentStatus] = mapped_column(
        Enum(PunishmentStatus, name="punishment_status"), default=PunishmentStatus.ISSUED
    )
    # Set when type is PENANCE_TASK — the Task whose PASS settles this punishment.
    # Bare UUID (no FK), matching the codebase convention for cross-aggregate refs
    # (cf. Task.lesson_id); task rows are only deleted via the whole-profile cascade.
    penance_task_id: Mapped[uuid.UUID | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    profile: Mapped[SubProfile] = relationship()
