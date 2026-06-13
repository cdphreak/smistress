from sqlalchemy import select

from app.chat import tools
from app.db.enums import TaskStatus
from app.db.models.task import Task
from app.economy import service as econ_svc
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc

_PASS_VERDICT = ChatResult(
    content='{"verdict": "pass", "confidence": 92, "reasoning": "credible report", "issues": []}'
)


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def _assign(session, profile_id, proof="honor", merit_reward=10):
    await tools.execute_action(
        session,
        profile_id,
        {"tool": "assign_task", "description": "Recite your purpose", "proof": proof,
         "merit_reward": merit_reward},
    )


async def test_complete_task_verifies_active_honor_task(session):
    p = await _profile(session)
    await _assign(session, p.id)
    provider = MockLLMProvider(scripted=[_PASS_VERDICT])

    card = await tools.execute_action(
        session, p.id, {"tool": "complete_task"},
        report="I knelt and recited it aloud; it felt grounding.", provider=provider,
    )

    assert card["tool"] == "complete_task"
    assert card["status"] == "verified_pass"
    assert card["verdict"] == "pass"
    task = (await session.execute(select(Task).where(Task.profile_id == p.id))).scalars().first()
    assert task.status is TaskStatus.VERIFIED_PASS
    # the verifier verdict drove the economy (merit reward applied on pass)
    assert (await econ_svc.get_economy(session, p.id)).merit > 0


async def test_complete_task_with_no_active_task_returns_error(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[_PASS_VERDICT])
    card = await tools.execute_action(
        session, p.id, {"tool": "complete_task"}, report="done", provider=provider
    )
    assert "error" in card
    assert "no active task" in card["error"]


async def test_complete_task_rejects_non_honor_proof(session):
    p = await _profile(session)
    await _assign(session, p.id, proof="photo")
    provider = MockLLMProvider(scripted=[_PASS_VERDICT])

    card = await tools.execute_action(
        session, p.id, {"tool": "complete_task"}, report="here it is", provider=provider
    )

    assert "error" in card
    assert "photo" in card["error"]
    # the task is untouched — media proof still goes through the task surface
    task = (await session.execute(select(Task).where(Task.profile_id == p.id))).scalars().first()
    assert task.status is TaskStatus.ASSIGNED
