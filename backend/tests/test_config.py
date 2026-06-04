from app.config import Settings


def test_vision_disabled_when_no_vision_model():
    s = Settings(vision_model=None)
    assert s.vision_enabled is False


def test_vision_enabled_when_vision_model_set():
    s = Settings(vision_model="gpt-4o")
    assert s.vision_enabled is True


def test_defaults_present():
    s = Settings()
    assert s.chat_model
    assert s.database_url.startswith("postgresql")
