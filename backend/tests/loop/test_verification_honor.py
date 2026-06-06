from app.config import Settings
from app.db.enums import ProofRequirement
from app.db.models.task import Task
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.loop.verification import verify, verify_honor


def _task(pr=ProofRequirement.HONOR) -> Task:
    return Task(description="20 push-ups", proof_requirement=pr)


async def test_verify_honor_parses_strict_json_pass():
    provider = MockLLMProvider(scripted=[ChatResult(
        content='{"verdict": "pass", "confidence": 82, "reasoning": "credible", "issues": []}'
    )])
    v = await verify_honor("I did all twenty, slowly.", _task(), provider)
    assert v.verdict == "pass"
    assert v.confidence == 82
    # the strict rubric was sent to the model as the system prompt
    assert provider.calls[0][0].role == "system"
    assert "20 push-ups" in provider.calls[0][1].content


async def test_verify_honor_parses_fenced_json():
    provider = MockLLMProvider(scripted=[ChatResult(
        content='```json\n{"verdict": "fail", "confidence": 30, "reasoning": "vague", "issues": ["no detail"]}\n```'
    )])
    v = await verify_honor("did it", _task(), provider)
    assert v.verdict == "fail"
    assert v.issues == ["no detail"]


async def test_verify_honor_unparseable_demands_reproof():
    provider = MockLLMProvider(scripted=[ChatResult(content="I think that's fine, sure.")])
    v = await verify_honor("did it", _task(), provider)
    assert v.verdict == "re_proof"   # can't trust an unparseable verdict


async def test_verify_router_dispatches_by_requirement():
    # none -> pass without touching the provider
    provider = MockLLMProvider(scripted=[])
    v = await verify(_task(ProofRequirement.NONE), report="", timer=None,
                     provider=provider, settings=Settings())
    assert v.verdict == "pass"
    assert provider.calls == []  # router didn't call the LLM for a no-proof task
