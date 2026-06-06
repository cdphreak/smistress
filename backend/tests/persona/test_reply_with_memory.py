from app.llm.mock import MockLLMProvider
from app.llm.types import ChatMessage, ChatResult
from app.persona import service as persona_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc
from tests.memory.fakes import FakeMemoryStore


async def test_reply_injects_retrieved_memory_into_prompt(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.commit()

    store = FakeMemoryStore(facts=["she performs best on Monday mornings"])
    provider = MockLLMProvider(scripted=[ChatResult(content="Noted, student.")])
    conversation = [ChatMessage(role="user", content="How am I doing?")]

    result = await persona_svc.generate_reply(
        session, p.id, conversation, provider, store=store
    )
    assert result.content == "Noted, student."
    system_prompt = provider.calls[0][0].content
    assert "Monday mornings" in system_prompt   # retrieved memory reached the prompt


async def test_reply_degrades_when_store_fails(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.commit()

    store = FakeMemoryStore(fail=True)  # FalkorDB down
    provider = MockLLMProvider(scripted=[ChatResult(content="Still here, student.")])
    conversation = [ChatMessage(role="user", content="Hi")]

    # must not raise; memory section becomes "(none yet)"
    result = await persona_svc.generate_reply(
        session, p.id, conversation, provider, store=store
    )
    assert result.content == "Still here, student."
    assert "(none yet)" in provider.calls[0][0].content
