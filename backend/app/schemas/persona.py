from __future__ import annotations

from pydantic import BaseModel


class DispositionOut(BaseModel):
    band: str
    standing: int
    reason: str
    line: str
