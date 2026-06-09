from app.chat import tools
from app.db.enums import TaskStatus
from app.economy import service as econ_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


def test_parse_action_extracts_and_strips_block():
    text = 'Kneel and report, pet.\n```action\n{"tool": "grant_tokens", "amount": 2}\n```'
    clean, action = tools.parse_action(text)
    assert clean == "Kneel and report, pet."
    assert action == {"tool": "grant_tokens", "amount": 2}


def test_parse_action_no_block_returns_text_and_none():
    clean, action = tools.parse_action("Just words, no action.")
    assert clean == "Just words, no action."
    assert action is None


def test_parse_action_malformed_json_strips_block_and_returns_none():
    clean, action = tools.parse_action("Hi.\n```action\n{not json}\n```")
    assert clean == "Hi."
    assert action is None


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_execute_assign_task_creates_task(session):
    p = await _profile(session)
    card = await tools.execute_action(
        session,
        p.id,
        {"tool": "assign_task", "description": "Posture drill", "proof": "honor", "merit_reward": 10},
    )
    assert card["tool"] == "assign_task"
    assert card["description"] == "Posture drill"
    assert card["proof"] == "honor"
    from sqlalchemy import select

    from app.db.models.task import Task

    tasks = (await session.execute(select(Task).where(Task.profile_id == p.id))).scalars().all()
    assert len(tasks) == 1 and tasks[0].status is TaskStatus.ASSIGNED


async def test_execute_grant_tokens_and_chastity(session):
    p = await _profile(session)
    card = await tools.execute_action(session, p.id, {"tool": "grant_tokens", "amount": 3})
    assert card == {"tool": "grant_tokens", "amount": 3, "reason": ""}
    assert (await econ_svc.get_economy(session, p.id)).tokens == 3

    card = await tools.execute_action(
        session, p.id, {"tool": "set_chastity", "hours": 12, "reason": "discipline"}
    )
    assert card["tool"] == "set_chastity" and card["hours"] == 12
    assert (await econ_svc.chastity_status(session, p.id)).locked is True


async def test_execute_assign_task_normalizes_capitalized_proof(session):
    # Capable models often write "Honor"/"Timer"; the enum is lower-case.
    p = await _profile(session)
    card = await tools.execute_action(
        session, p.id, {"tool": "assign_task", "description": "kneel", "proof": "Honor"}
    )
    assert card.get("proof") == "honor"
    assert "error" not in card


async def test_execute_unknown_or_bad_returns_error_card(session):
    p = await _profile(session)
    assert (await tools.execute_action(session, p.id, {"tool": "nope"}))["error"]
    bad = await tools.execute_action(session, p.id, {"tool": "grant_tokens", "amount": 0})
    assert "error" in bad
