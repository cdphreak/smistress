from __future__ import annotations

from pydantic import BaseModel


class DroneNoticeOut(BaseModel):
    unit: str
    line: str


class StandingOrdersOut(BaseModel):
    notices: list[DroneNoticeOut]
