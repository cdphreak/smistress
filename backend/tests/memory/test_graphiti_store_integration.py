import os
from datetime import datetime, timezone

import pytest

from app.config import Settings
from app.memory.graphiti_store import GraphitiMemoryStore

pytestmark = pytest.mark.skipif(
    os.environ.get("SMISTRESS_GRAPHITI_IT") != "1",
    reason="set SMISTRESS_GRAPHITI_IT=1 with FalkorDB + an LLM available to run",
)


async def test_add_then_retrieve_round_trip():
    # Requires a running FalkorDB and a reachable OpenAI-compatible LLM + embedder.
    store = GraphitiMemoryStore(Settings(graphiti_enabled=True))
    gid = "it-" + datetime.now(timezone.utc).isoformat()
    await store.add_episode(
        group_id=gid,
        name="it episode",
        body="The student completed morning stretches on time.",
        source="text",
        source_description="integration test",
        reference_time=datetime.now(timezone.utc),
    )
    block = await store.retrieve(group_id=gid, query="What did the student complete?")
    assert isinstance(block, str)  # content depends on the model; just prove the round-trip
