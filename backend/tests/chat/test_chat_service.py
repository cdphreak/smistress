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


async def test_build_dossier_composes_economy_disposition_active_task(session):
    p = await _profile(session)
    d = await chat_svc.build_dossier(session, p.id)
    assert d["rank"] == "novice"
    assert d["merit"] == 0
    assert d["tokens"] == 0
    assert "band" in d["disposition"] and "line" in d["disposition"]
    assert d["active_task"] is None
    assert d["denial_timers"] == 0
