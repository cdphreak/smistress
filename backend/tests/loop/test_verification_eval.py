from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.db.enums import ProofRequirement
from app.db.models.loop import TaskTimer
from app.db.models.task import Task
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.loop.verification import verify
from tests.loop.fixtures import HONOR_CASES


@pytest.mark.parametrize("case", HONOR_CASES, ids=lambda c: c.name)
async def test_honor_verdict_parsing_matches_golden(case):
    provider = MockLLMProvider(scripted=[ChatResult(content=case.scripted_json)])
    task = Task(description="t", proof_requirement=ProofRequirement.HONOR)
    v = await verify(task, report=case.report, timer=None, provider=provider, settings=Settings())
    assert v.verdict == case.expected_verdict


async def test_timer_route_is_deterministic_no_llm():
    start = datetime.now(timezone.utc)
    timer = TaskTimer(required_seconds=300, started_at=start, stopped_at=start + timedelta(seconds=301))
    task = Task(description="t", proof_requirement=ProofRequirement.TIMER)
    provider = MockLLMProvider(scripted=[])  # must not be called
    v = await verify(task, report="", timer=timer, provider=provider, settings=Settings())
    assert v.verdict == "pass"
    assert provider.calls == []


async def test_media_autopass_invariant_without_vision():
    task = Task(description="t", proof_requirement=ProofRequirement.PHOTO)
    v = await verify(task, report="", timer=None,
                     provider=MockLLMProvider(), settings=Settings(vision_model=None))
    assert v.verdict == "pass"  # configurable-vision seam: auto-pass when no vision model
