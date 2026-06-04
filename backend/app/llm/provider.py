from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.llm.types import ChatMessage, ChatResult


@runtime_checkable
class LLMProvider(Protocol):
    supports_vision: bool

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> ChatResult: ...
