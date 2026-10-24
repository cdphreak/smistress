from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SettlementOut(BaseModel):
    judged: int
    passed: int
    failed: int
    re_proven: int
    skipped: int
    errored: int
    memory_drained: int

    model_config = ConfigDict(from_attributes=True)
