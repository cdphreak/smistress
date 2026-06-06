from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.db.enums import ProofRequirement, TaskStatus


class TaskCreate(BaseModel):
    description: str
    proof_requirement: ProofRequirement = ProofRequirement.HONOR
    deadline: datetime | None = None
    merit_reward: int = 0
    merit_fail_penalty: int = 0
    merit_miss_penalty: int = 0
    required_seconds: int | None = None  # for timer proofs


class TaskOut(BaseModel):
    id: UUID
    description: str
    proof_requirement: ProofRequirement
    status: TaskStatus
    deadline: datetime | None
    merit_reward: int
    merit_fail_penalty: int
    merit_miss_penalty: int
    model_config = ConfigDict(from_attributes=True)


class ProofIn(BaseModel):
    report: str = ""


class VerdictOut(BaseModel):
    task_id: UUID
    status: TaskStatus
    verdict: str | None
    confidence: int | None
    reasoning: str
