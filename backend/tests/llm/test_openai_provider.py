from types import SimpleNamespace

from app.llm.openai_provider import OpenAICompatibleProvider
from app.llm.types import ChatMessage


class _FakeCompletions:
    def __init__(self, message):
        self._message = message
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=self._message)])


def _fake_client(message):
    return SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(message)))


async def test_parses_plain_content():
    client = _fake_client(SimpleNamespace(content="hi there", tool_calls=None))
    p = OpenAICompatibleProvider(
        base_url="x", api_key="x", default_model="m", supports_vision=False, client=client
    )
    r = await p.chat([ChatMessage(role="user", content="yo")])
    assert r.content == "hi there"
    assert r.tool_calls == []
    assert client.chat.completions.kwargs["model"] == "m"


async def test_parses_tool_calls_and_model_override():
    tc = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="assign_task", arguments='{"title":"x"}'),
    )
    client = _fake_client(SimpleNamespace(content=None, tool_calls=[tc]))
    p = OpenAICompatibleProvider(
        base_url="x", api_key="x", default_model="m", supports_vision=True, client=client
    )
    r = await p.chat([ChatMessage(role="user", content="yo")], model="other")
    assert r.content == ""
    assert r.tool_calls[0].name == "assign_task"
    assert client.chat.completions.kwargs["model"] == "other"


async def test_formats_multipart_when_images_present():
    client = _fake_client(SimpleNamespace(content="ok", tool_calls=None))
    p = OpenAICompatibleProvider(
        base_url="x", api_key="x", default_model="m", supports_vision=True, client=client
    )
    await p.chat([ChatMessage(role="user", content="judge this", images=["data:image/png;base64,AAA"])])
    sent = client.chat.completions.kwargs["messages"][0]["content"]
    assert isinstance(sent, list)
    assert any(part.get("type") == "text" for part in sent)
    assert any(part.get("type") == "image_url" for part in sent)


async def test_plain_string_content_when_no_images():
    client = _fake_client(SimpleNamespace(content="ok", tool_calls=None))
    p = OpenAICompatibleProvider(
        base_url="x", api_key="x", default_model="m", supports_vision=False, client=client
    )
    await p.chat([ChatMessage(role="user", content="yo")])
    assert client.chat.completions.kwargs["messages"][0]["content"] == "yo"
