from app.config import Settings
from app.llm.factory import build_provider
from app.llm.mock import MockLLMProvider
from app.llm.openai_provider import OpenAICompatibleProvider


def test_factory_returns_mock_when_base_url_is_mock():
    p = build_provider(Settings(llm_base_url="mock", vision_model="gpt-4o"))
    assert isinstance(p, MockLLMProvider)
    assert p.supports_vision is True  # mirrors vision_enabled


def test_factory_returns_openai_provider_otherwise():
    p = build_provider(Settings(llm_base_url="http://localhost:11434/v1", vision_model=None))
    assert isinstance(p, OpenAICompatibleProvider)
    assert p.supports_vision is False
