from app.chat import service as chat_svc
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.memory.store import NullMemoryStore
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def test_post_message_stores_turn_and_returns_reply(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[ChatResult(content="On the board, pet.")])
    reply = await chat_svc.post_message(
        session, p.id, "what is my task?", provider, NullMemoryStore()
    )
    assert reply.role == "assistant"
    assert reply.content == "On the board, pet."

    history = await chat_svc.list_messages(session, p.id)
    assert [(m.role, m.content) for m in history] == [
        ("user", "what is my task?"),
        ("assistant", "On the board, pet."),
    ]


async def test_post_message_sends_prior_history_to_the_model(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[ChatResult(content="one"), ChatResult(content="two")])
    await chat_svc.post_message(session, p.id, "first", provider, NullMemoryStore())
    await chat_svc.post_message(session, p.id, "second", provider, NullMemoryStore())
    # the 2nd call's conversation (sans system prompt) carries the full prior turns
    sent = provider.calls[1]
    contents = [m.content for m in sent if m.role != "system"]
    assert contents == ["first", "one", "second"]


async def test_post_message_executes_action_and_strips_block(session):
    from sqlalchemy import select

    from app.db.models.task import Task

    p = await _profile(session)
    scripted = (
        "On the board, pet.\n"
        '```action\n{"tool": "assign_task", "description": "Posture drill", '
        '"proof": "honor", "merit_reward": 10}\n```'
    )
    provider = MockLLMProvider(scripted=[ChatResult(content=scripted)])
    reply = await chat_svc.post_message(session, p.id, "give me a task", provider, NullMemoryStore())

    assert reply.content == "On the board, pet."  # block stripped
    assert reply.action["tool"] == "assign_task"  # action recorded
    tasks = (await session.execute(select(Task).where(Task.profile_id == p.id))).scalars().all()
    assert len(tasks) == 1  # task actually created


async def test_post_message_without_action_has_none(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[ChatResult(content="Just words.")])
    reply = await chat_svc.post_message(session, p.id, "hi", provider, NullMemoryStore())
    assert reply.content == "Just words."
    assert reply.action is None


async def test_build_dossier_composes_economy_disposition_active_task(session):
    p = await _profile(session)
    d = await chat_svc.build_dossier(session, p.id)
    assert d["rank"] == "novice"
    assert d["merit"] == 0
    assert d["tokens"] == 0
    assert "band" in d["disposition"] and "line" in d["disposition"]
    assert d["active_task"] is None
    assert d["debt"] == 0
    assert d["chastity"]["locked"] is False
    assert d["denial_timers"] == 0


async def test_build_dossier_reflects_active_chastity_lock(session):
    from datetime import datetime, timedelta, timezone

    from app.economy import service as econ_svc

    p = await _profile(session)
    await econ_svc.set_chastity(
        session, p.id, ends_at=datetime.now(timezone.utc) + timedelta(hours=4)
    )
    d = await chat_svc.build_dossier(session, p.id)
    assert d["chastity"]["locked"] is True
    assert d["chastity"]["seconds_remaining"] > 0
    assert d["denial_timers"] == 1  # compat count reflects the single lock
