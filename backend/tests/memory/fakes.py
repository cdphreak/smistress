from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class RecordedEpisode:
    group_id: str
    name: str
    body: str
    source: str
    source_description: str
    reference_time: datetime


class FakeMemoryStore:
    """In-memory MemoryStore for tests. Optionally raises to simulate FalkorDB down."""

    def __init__(self, *, facts: list[str] | None = None, fail: bool = False) -> None:
        self.episodes: list[RecordedEpisode] = []
        self._facts = facts or []
        self.fail = fail

    async def add_episode(
        self, *, group_id, name, body, source, source_description, reference_time
    ) -> None:
        if self.fail:
            raise RuntimeError("FalkorDB unavailable")
        self.episodes.append(
            RecordedEpisode(group_id, name, body, source, source_description, reference_time)
        )

    async def retrieve(self, *, group_id, query, num_results=10) -> str:
        if self.fail:
            raise RuntimeError("FalkorDB unavailable")
        return "\n".join(f"- {f}" for f in self._facts)
