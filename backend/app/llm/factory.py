from __future__ import annotations

from app.config import Settings
from app.llm.mock import MockLLMProvider
from app.llm.openai_provider import OpenAICompatibleProvider
from app.llm.provider import LLMProvider


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_base_url == "mock":
        return MockLLMProvider(supports_vision=settings.vision_enabled)
    return OpenAICompatibleProvider(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        default_model=settings.chat_model,
        supports_vision=settings.vision_enabled,
    )
