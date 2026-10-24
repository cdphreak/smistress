from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.db.models.loop import TaskTimer
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.loop.verification import verify_media, verify_none, verify_timer


def test_verify_none_auto_passes():
    v = verify_none()
    assert v.verdict == "pass"


def test_verify_timer_pass_when_enough_elapsed():
    start = datetime.now(timezone.utc)
    timer = TaskTimer(required_seconds=600, started_at=start, stopped_at=start + timedelta(seconds=700))
    v = verify_timer(timer)
    assert v.verdict == "pass"
    assert v.confidence == 100


def test_verify_timer_fail_when_too_short():
    start = datetime.now(timezone.utc)
    timer = TaskTimer(required_seconds=600, started_at=start, stopped_at=start + timedelta(seconds=120))
    v = verify_timer(timer)
    assert v.verdict == "fail"
    assert "insufficient" in v.issues[0].lower()


def test_verify_timer_reproof_when_not_stopped():
    timer = TaskTimer(required_seconds=600, started_at=datetime.now(timezone.utc), stopped_at=None)
    v = verify_timer(timer)
    assert v.verdict == "re_proof"


def _photo_task():
    from app.db.enums import ProofRequirement
    from app.db.models.task import Task
    return Task(description="send kneeling photo", proof_requirement=ProofRequirement.PHOTO)


async def test_verify_media_autopasses_without_vision():
    v = await verify_media(_photo_task(), media_uri="u", provider=MockLLMProvider(),
                           settings=Settings(vision_model=None))
    assert v.verdict == "pass"
    assert v.confidence is None
    assert "auto" in v.reasoning.lower()


async def test_verify_media_pending_when_vision_configured_but_provider_lacks_vision():
    v = await verify_media(_photo_task(), media_uri="u",
                           provider=MockLLMProvider(supports_vision=False),
                           settings=Settings(vision_model="qwen2.5-vl"))
    assert v.verdict == "pending_review"


async def test_verify_media_judges_pass_via_vision_provider():
    prov = MockLLMProvider(supports_vision=True, scripted=[ChatResult(
        content='{"verdict": "pass", "confidence": 88, "reasoning": "visible", "issues": []}'
    )])
    v = await verify_media(_photo_task(), media_uri="data:image/png;base64,AAA",
                           provider=prov, settings=Settings(vision_model="qwen2.5-vl"))
    assert v.verdict == "pass"
    assert v.confidence == 88
    assert prov.calls and prov.calls[-1][-1].images == ["data:image/png;base64,AAA"]


async def test_verify_media_judges_fail_via_vision_provider():
    prov = MockLLMProvider(supports_vision=True, scripted=[ChatResult(
        content='{"verdict": "fail", "confidence": 30, "reasoning": "absent", "issues": ["no subject"]}'
    )])
    v = await verify_media(_photo_task(), media_uri="u", provider=prov,
                           settings=Settings(vision_model="qwen2.5-vl"))
    assert v.verdict == "fail"


async def test_verify_media_unparseable_vision_response_demands_reproof():
    prov = MockLLMProvider(supports_vision=True, scripted=[ChatResult(content="looks fine")])
    v = await verify_media(_photo_task(), media_uri="u", provider=prov,
                           settings=Settings(vision_model="qwen2.5-vl"))
    assert v.verdict == "re_proof"


async def test_verify_routes_photo_to_pending_review_when_vision_enabled():
    from app.db.enums import ProofRequirement
    from app.db.models.task import Task
    from app.loop.verification import verify
    from app.llm.mock import MockLLMProvider

    task = Task(description="x", proof_requirement=ProofRequirement.VIDEO)
    v = await verify(task, report="", timer=None,
                     provider=MockLLMProvider(), settings=Settings(vision_model="qwen2.5-vl"))
    assert v.verdict == "pending_review"


async def test_verify_routes_photo_to_pass_when_no_vision():
    from app.db.enums import ProofRequirement
    from app.db.models.task import Task
    from app.loop.verification import verify
    from app.llm.mock import MockLLMProvider

    task = Task(description="x", proof_requirement=ProofRequirement.PHOTO)
    v = await verify(task, report="", timer=None,
                     provider=MockLLMProvider(), settings=Settings())
    assert v.verdict == "pass"


async def test_verify_media_forwards_configured_vision_model_to_provider():
    # Spy: records the model= kwarg verify_media forwards, then delegates to the
    # stock mock to replay the scripted verdict.
    class _SpyProvider(MockLLMProvider):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.observed_model: str | None = "UNSET"

        async def chat(self, messages, *, model=None, tools=None):
            self.observed_model = model
            return await super().chat(messages, model=model, tools=tools)

    spy = _SpyProvider(supports_vision=True, scripted=[ChatResult(
        content='{"verdict": "pass", "confidence": 88, "reasoning": "ok", "issues": []}'
    )])
    v = await verify_media(
        _photo_task(),
        media_uri="data:image/png;base64,AAA",
        provider=spy,
        settings=Settings(vision_model="qwen2.5-vl"),
    )
    assert v.verdict == "pass"
    assert spy.observed_model == "qwen2.5-vl"
