from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.db.enums import LLMAvailability


class HeartbeatIn(BaseModel):
    source: str = ""  # optional label, e.g. "<host>:<model>"; for display only


class AvailabilityOut(BaseModel):
    state: LLMAvailability
    online: bool
    last_heartbeat_at: datetime | None = None
