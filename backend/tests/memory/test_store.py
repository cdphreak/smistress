from app.config import Settings
from app.memory.store import NullMemoryStore, build_memory_store, retrieve_memory
from tests.memory.fakes import FakeMemoryStore


def test_factory_returns_null_when_disabled():
    store = build_memory_store(Settings(graphiti_enabled=False))
    assert isinstance(store, NullMemoryStore)


async def test_null_store_is_noop():
    store = NullMemoryStore()
    await store.add_episode(
        group_id="g", name="n", body="b", source="text",
        source_description="d", reference_time=__import__("datetime").datetime.now(),
    )
    assert await store.retrieve(group_id="g", query="q") == ""


async def test_retrieve_memory_returns_facts_block():
    store = FakeMemoryStore(facts=["she prefers morning tasks", "missed Tuesday"])
    block = await retrieve_memory(store, group_id="g", query="patterns?")
    assert "morning tasks" in block
    assert "missed Tuesday" in block


async def test_retrieve_memory_degrades_to_empty_on_error():
    store = FakeMemoryStore(fail=True)
    # a store failure must NEVER break the turn -> empty memory, no exception
    assert await retrieve_memory(store, group_id="g", query="x") == ""
