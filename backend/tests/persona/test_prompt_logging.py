import logging

from app.db.enums import KinkRating
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatMessage, ChatResult
from app.persona import service as persona_svc
from app.schemas.onboarding import KinkItem, ProfileCreate
from app.services import profile as profile_svc

_PROMPT_LOGGER = "app.persona.prompt"


async def _make_profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await profile_svc.replace_kinks(
        session, p.id, [KinkItem(kink="blood", rating=KinkRating.HARD_LIMIT)]
    )
    await session.commit()
    return p


async def test_logs_assembled_prompt_when_enabled(session, monkeypatch, caplog):
    p = await _make_profile(session)
    monkeypatch.setattr(persona_svc._settings, "log_prompts", True)

    provider = MockLLMProvider(scripted=[ChatResult(content="On the board.")])
    conversation = [ChatMessage(role="user", content="What's my task?")]
    with caplog.at_level(logging.INFO, logger=_PROMPT_LOGGER):
        await persona_svc.generate_reply(session, p.id, conversation, provider)

    logged = "\n".join(r.getMessage() for r in caplog.records if r.name == _PROMPT_LOGGER)
    assert "WHO YOU ARE" in logged  # the compiled system prompt
    assert "blood" in logged  # the hard limit carried in the authoritative state
    assert "What's my task?" in logged  # the conversation turn


async def test_does_not_log_when_disabled(session, monkeypatch, caplog):
    p = await _make_profile(session)
    monkeypatch.setattr(persona_svc._settings, "log_prompts", False)

    provider = MockLLMProvider(scripted=[ChatResult(content="hi")])
    with caplog.at_level(logging.INFO, logger=_PROMPT_LOGGER):
        await persona_svc.generate_reply(
            session, p.id, [ChatMessage(role="user", content="hello")], provider
        )

    assert not [r for r in caplog.records if r.name == _PROMPT_LOGGER]
