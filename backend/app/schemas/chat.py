from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ChatPost(BaseModel):
    content: str


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    action: dict | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DispositionBlock(BaseModel):
    band: str
    line: str
    reason: str
    standing: int


class ActiveTask(BaseModel):
    description: str
    status: str


class ChastityBlock(BaseModel):
    locked: bool
    ends_at: str | None
    seconds_remaining: int


class DossierOut(BaseModel):
    rank: str
    merit: int
    tokens: int
    debt: int
    disposition: DispositionBlock
    active_task: ActiveTask | None
    chastity: ChastityBlock
