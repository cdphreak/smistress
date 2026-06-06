from app.config import Settings


def test_memory_settings_defaults():
    s = Settings()
    assert s.graphiti_enabled is False          # default off -> NullMemoryStore
    assert s.embedding_model                      # has a default
    assert s.embedding_dim > 0
    assert s.falkordb_host
    assert s.falkordb_port > 0
