"""End-to-end seam: generate_batch -> draw_and_assign -> drone line rendering.

The unit tests cover each stage in isolation; this exercises the full offline
loop — a generated DroneLine with a {task} placeholder must flow through the
drone engine and render with the description of a task drawn from the pool.
"""
import json

from app.batch import service as batch_svc
from app.drones import service as drone_svc
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_full_generate_draw_serve_pipeline(session):
    p = await _profile(session)
    payload = ChatResult(content=json.dumps({
        "tasks": [
            {"description": "Drawn drill", "proof": "honor", "merit_reward": 5},
        ],
        "lines": [
            {"unit": "assignment", "event": "task_drop", "merit_band": "any",
             "time_of_day": "any", "text": "UNIT-3 assigns: {task}."},
        ],
    }))
    provider = MockLLMProvider(scripted=[payload])

    # 1. Generate seeds the pool + line bank.
    result = await batch_svc.generate_batch(session, p.id, provider)
    assert result.tasks_added == 1
    assert result.lines_added == 1

    # 2 + 3. The drone engine draws the pooled task and renders the bank line.
    notices = await drone_svc.standing_orders(session, p.id)
    assignment = [n for n in notices if n.unit == "assignment"][0]
    assert assignment.line == "UNIT-3 assigns: Drawn drill."
