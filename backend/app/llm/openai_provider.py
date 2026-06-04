from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from app.llm.types import ChatMessage, ChatResult, ToolCall


class OpenAICompatibleProvider:
    """Talks to any OpenAI Chat Completions-compatible endpoint (OpenAI, Ollama, vLLM, ...)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        default_model: str,
        supports_vision: bool,
        client: Any | None = None,
    ) -> None:
        self._client = client or AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._default_model = default_model
        self.supports_vision = supports_vision

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> ChatResult:
        resp = await self._client.chat.completions.create(
            model=model or self._default_model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            tools=tools or None,
        )
        choice = resp.choices[0].message
        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
            for tc in (choice.tool_calls or [])
        ]
        return ChatResult(content=choice.content or "", tool_calls=tool_calls)
