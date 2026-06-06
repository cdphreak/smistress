from __future__ import annotations

import logging
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.config import Settings

logger = logging.getLogger(__name__)


@runtime_checkable
class MemoryStore(Protocol):
    async def add_episode(
        self,
        *,
        group_id: str,
        name: str,
        body: str,
        source: str,
        source_description: str,
        reference_time: datetime,
    ) -> None: ...

    async def retrieve(self, *, group_id: str, query: str, num_results: int = 10) -> str: ...


class NullMemoryStore:
    """No-op store: used when graphiti is disabled and as the degradation fallback."""

    async def add_episode(self, **_kwargs) -> None:
        return None

    async def retrieve(self, **_kwargs) -> str:
        return ""


def build_memory_store(settings: Settings) -> MemoryStore:
    if not settings.graphiti_enabled:
        return NullMemoryStore()
    from app.memory.graphiti_store import GraphitiMemoryStore  # lazy: heavy import

    return GraphitiMemoryStore(settings)


async def retrieve_memory(store: MemoryStore, *, group_id: str, query: str) -> str:
    """Retrieve a memory block, degrading to '' on any store failure (spec 3)."""
    try:
        return await store.retrieve(group_id=group_id, query=query)
    except Exception:  # noqa: BLE001 - degradation must catch everything
        logger.warning("memory retrieval failed; degrading to no memory", exc_info=True)
        return ""
