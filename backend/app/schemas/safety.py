from __future__ import annotations

from pydantic import BaseModel

from app.db.enums import KinkRating


class StopReceiptOut(BaseModel):
    scene_halted: bool
    denial_lifted: int
    merit_penalty: int
    aftercare: str
    message: str


class SafetyStateOut(BaseModel):
    is_halted: bool
    on_hiatus: bool
    consent_check_due: bool


class HiatusIn(BaseModel):
    on: bool


class LowerLimitIn(BaseModel):
    kink: str
    rating: KinkRating


class LowerLimitOut(BaseModel):
    kink: str
    rating: KinkRating
