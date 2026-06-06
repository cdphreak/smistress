from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DenialTimerOut(BaseModel):
    id: UUID
    reason: str
    ends_at: datetime
    active: bool
    model_config = ConfigDict(from_attributes=True)


class StandingOut(BaseModel):
    merit: int
    rank: str
    tokens: int
    denial_timers: list[DenialTimerOut]


class TokenOp(BaseModel):
    amount: int = Field(ge=1)


class DenialTimerIn(BaseModel):
    reason: str = ""
    ends_at: datetime
