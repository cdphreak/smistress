from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.profile import SubProfile


class Message(Base):
    """A single chat turn (spec 5A / Addendum A5). role is 'user' | 'assistant'.

    The system prompt is recompiled per turn and never stored; only the visible
    conversation is persisted, so reload and memory can reference it.
    """

    __tablename__ = "message"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_profile.id"))
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    # Executed tool-action card for an assistant turn (B2); null for plain replies.
    action: Mapped[dict | None] = mapped_column(JSONB, default=None, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    profile: Mapped[SubProfile] = relationship()
