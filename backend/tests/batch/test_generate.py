import json

from app.batch import service as batch_svc
from app.db.enums import ProofRequirement
from app.db.models.batch import DroneLine, TaskPoolItem
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from sqlalchemy import func, select


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


def _payload(n_tasks=3, n_lines=4, n_punishments=3):
    return ChatResult(content=json.dumps({
        "tasks": [
            {"description": f"task {i}", "proof": "honor", "merit_reward": 5,
             "merit_miss_penalty": 3, "difficulty": "standard"}
            for i in range(n_tasks)
        ],
        "lines": [
            {"unit": "assignment", "event": "task_drop", "merit_band": "mid",
             "time_of_day": "any", "text": "Mistress has set you: {task}."}
            for _ in range(n_lines)
        ],
        "punishments": [
            {"type": "penance_task", "severity": 2, "reason": f"penance {i}"}
            for i in range(n_punishments)
        ],
    }))


async def test_generate_persists_parsed_artifacts(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[_payload(3, 4)])
    result = await batch_svc.generate_batch(session, p.id, provider)
    assert result.tasks_added == 3
    assert result.lines_added == 4
    tasks = (await session.execute(
        select(func.count()).select_from(TaskPoolItem).where(TaskPoolItem.profile_id == p.id)
    )).scalar_one()
    assert tasks == 3
    lines = (await session.execute(
        select(func.count()).select_from(DroneLine).where(DroneLine.profile_id == p.id)
    )).scalar_one()
    assert lines == 4
    from app.db.models.batch import PunishmentPoolItem
    punishments = (await session.execute(
        select(func.count()).select_from(PunishmentPoolItem)
        .where(PunishmentPoolItem.profile_id == p.id)
    )).scalar_one()
    assert punishments == 3
    assert result.punishments_added == 3


async def test_generate_tops_up_only_to_target(session):
    p = await _profile(session)
    for i in range(7):
        session.add(TaskPoolItem(
            profile_id=p.id, description=f"have {i}", proof_requirement=ProofRequirement.HONOR
        ))
    await session.flush()
    provider = MockLLMProvider(scripted=[_payload(5, 0)])
    result = await batch_svc.generate_batch(session, p.id, provider)
    assert result.tasks_added == 1  # 8 target - 7 existing


async def test_generate_skips_malformed_items(session):
    p = await _profile(session)
    bad = ChatResult(content=json.dumps({
        "tasks": [
            {"description": "ok", "proof": "honor"},
            {"description": "bad proof", "proof": "telepathy"},
            {"proof": "honor"},
        ],
        "lines": [{"unit": "assignment", "event": "task_drop", "text": "x"}],
    }))
    provider = MockLLMProvider(scripted=[bad])
    result = await batch_svc.generate_batch(session, p.id, provider)
    assert result.tasks_added == 1
    assert result.lines_added == 1  # the one valid line parses through the same path


async def test_generate_handles_non_json_gracefully(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[ChatResult(content="I am away; no JSON here.")])
    result = await batch_svc.generate_batch(session, p.id, provider)
    assert result.tasks_added == 0
    assert result.lines_added == 0


async def test_generate_handles_non_list_collections_gracefully(session):
    # A malformed model reply where tasks/lines are not arrays must not raise.
    p = await _profile(session)
    bad = ChatResult(content=json.dumps({"tasks": 42, "lines": "nope"}))
    provider = MockLLMProvider(scripted=[bad])
    result = await batch_svc.generate_batch(session, p.id, provider)
    assert result.tasks_added == 0
    assert result.lines_added == 0
