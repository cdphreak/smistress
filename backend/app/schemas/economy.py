from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChastityOut(BaseModel):
    locked: bool
    ends_at: datetime | None
    seconds_remaining: int


class StandingOut(BaseModel):
    merit: int
    rank: str
    tokens: int
    debt: int
    chastity: ChastityOut


class TokenOp(BaseModel):
    amount: int = Field(ge=1)


class SetChastityIn(BaseModel):
    hours: int = Field(ge=1)
    note: str = ""


class BuyDownIn(BaseModel):
    debt_points: int = Field(ge=1)
