from __future__ import annotations

from app.llm.types import ChatMessage, ChatResult


class MockLLMProvider:
    """In-memory provider for tests and the "mock" base_url. Records calls; replays scripted results."""

    def __init__(
        self,
        *,
        supports_vision: bool = False,
        scripted: list[ChatResult] | None = None,
    ) -> None:
        self.supports_vision = supports_vision
        self._scripted = list(scripted or [])
        self.calls: list[list[ChatMessage]] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> ChatResult:
        self.calls.append(list(messages))
        if self._scripted:
            return self._scripted.pop(0)
        return ChatResult(content="ok")
