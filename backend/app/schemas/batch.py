from __future__ import annotations

from pydantic import BaseModel


class GenerateBatchOut(BaseModel):
    tasks_added: int
    lines_added: int
    punishments_added: int
    task_pool: int
    line_bank: int
    punishment_pool: int


class PoolStatusOut(BaseModel):
    task_pool: int
    line_bank: int
    punishment_pool: int
    task_pool_low: bool
    line_bank_low: bool
    punishment_pool_low: bool
