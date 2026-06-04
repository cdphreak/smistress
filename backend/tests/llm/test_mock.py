from app.llm.mock import MockLLMProvider
from app.llm.provider import LLMProvider
from app.llm.types import ChatMessage, ChatResult


def test_mock_satisfies_protocol():
    assert isinstance(MockLLMProvider(), LLMProvider)


async def test_mock_returns_scripted_result_and_records_calls():
    p = MockLLMProvider(scripted=[ChatResult(content="hello")])
    r = await p.chat([ChatMessage(role="user", content="hi")])
    assert r.content == "hello"
    assert p.calls[0][0].content == "hi"


async def test_mock_default_result_when_unscripted():
    p = MockLLMProvider()
    r = await p.chat([ChatMessage(role="user", content="hi")])
    assert r.content == "ok"


def test_mock_vision_flag():
    assert MockLLMProvider(supports_vision=True).supports_vision is True
