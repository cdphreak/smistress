from app.agent import heartbeat


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeClient:
    """Records calls and returns scripted responses; raises if told to."""

    def __init__(self, *, get_status=200, post_status=200, raise_on_get=False):
        self.get_status = get_status
        self.post_status = post_status
        self.raise_on_get = raise_on_get
        self.posts: list[tuple[str, dict]] = []

    async def get(self, url, **kwargs):
        if self.raise_on_get:
            import httpx

            raise httpx.ConnectError("boom")
        return _FakeResponse(self.get_status)

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs.get("json", {})))
        return _FakeResponse(self.post_status)


async def test_llm_reachable_true_on_200():
    client = _FakeClient(get_status=200)
    assert await heartbeat.llm_reachable(client, "http://localhost:11434/v1") is True


async def test_llm_reachable_false_on_error():
    client = _FakeClient(raise_on_get=True)
    assert await heartbeat.llm_reachable(client, "http://localhost:11434/v1") is False


async def test_run_once_beats_when_reachable():
    client = _FakeClient(get_status=200, post_status=200)
    sent = await heartbeat.run_once(
        client,
        llm_base_url="http://localhost:11434/v1",
        vps_url="https://vps.example",
        source="qwen",
    )
    assert sent is True
    assert client.posts == [("https://vps.example/llm/heartbeat", {"source": "qwen"})]


async def test_run_once_skips_when_unreachable():
    client = _FakeClient(raise_on_get=True)
    sent = await heartbeat.run_once(
        client,
        llm_base_url="http://localhost:11434/v1",
        vps_url="https://vps.example",
        source="qwen",
    )
    assert sent is False
    assert client.posts == []


async def test_run_once_returns_false_when_post_fails():
    client = _FakeClient(get_status=200, post_status=503)
    sent = await heartbeat.run_once(
        client,
        llm_base_url="http://localhost:11434/v1",
        vps_url="https://vps.example",
        source="qwen",
    )
    assert sent is False
    # it still attempted the POST
    assert client.posts == [("https://vps.example/llm/heartbeat", {"source": "qwen"})]
