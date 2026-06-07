from app.db.enums import KinkRating
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatMessage, ChatResult
from app.persona import service as persona_svc
from app.safety import service as safety_svc
from app.schemas.onboarding import KinkItem, ProfileCreate
from app.services import profile as profile_svc


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await profile_svc.replace_kinks(session, p.id, [KinkItem(kink="blood", rating=KinkRating.HARD_LIMIT)])
    await session.commit()
    return p


async def test_safeword_intercepts_before_llm(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[ChatResult(content="should never be sent")])
    result = await persona_svc.generate_reply(
        session, p.id, [ChatMessage(role="user", content="red")], provider
    )
    assert provider.calls == []                       # LLM never called
    assert "stopping" in result.content.lower()
    assert (await safety_svc.get_or_create_state(session, p.id)).is_halted is True


async def test_crisis_breaks_character_before_llm(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[ChatResult(content="nope")])
    result = await persona_svc.generate_reply(
        session, p.id, [ChatMessage(role="user", content="I want to die")], provider
    )
    assert provider.calls == []
    assert "988" in result.content


async def test_halted_stays_in_hold(session):
    p = await _profile(session)
    await safety_svc.trigger_stop(session, p.id)
    provider = MockLLMProvider(scripted=[ChatResult(content="nope")])
    result = await persona_svc.generate_reply(
        session, p.id, [ChatMessage(role="user", content="what now?")], provider
    )
    assert provider.calls == []
    assert "paused" in result.content.lower()


async def test_output_filter_regenerates_then_passes(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[
        ChatResult(content="Bring me blood."),       # violates hard limit
        ChatResult(content="Bring me your full attention."),  # clean retry
    ])
    result = await persona_svc.generate_reply(
        session, p.id, [ChatMessage(role="user", content="task?")], provider
    )
    assert len(provider.calls) == 2
    assert result.content == "Bring me your full attention."


async def test_output_filter_redacts_when_retry_still_violates(session):
    p = await _profile(session)
    provider = MockLLMProvider(scripted=[
        ChatResult(content="Bring me blood."),
        ChatResult(content="More blood."),
    ])
    result = await persona_svc.generate_reply(
        session, p.id, [ChatMessage(role="user", content="task?")], provider
    )
    assert len(provider.calls) == 2
    assert "hard limit" in result.content.lower()
    from app.safety import filter as sf
    assert result.content == sf.SAFE_REPLY
