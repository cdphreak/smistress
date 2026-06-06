from app.db.enums import KinkRating
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatMessage, ChatResult
from app.persona import service as persona_svc
from app.schemas.onboarding import KinkItem, ProfileCreate
from app.services import profile as profile_svc


async def test_generate_reply_prepends_compiled_system_prompt(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    await profile_svc.replace_kinks(session, p.id, [
        KinkItem(kink="blood", rating=KinkRating.HARD_LIMIT),
    ])
    await session.commit()

    provider = MockLLMProvider(scripted=[ChatResult(content="On the board, student.")])
    conversation = [ChatMessage(role="user", content="What's my task?")]
    result = await persona_svc.generate_reply(session, p.id, conversation, provider)

    assert result.content == "On the board, student."
    # the provider received system prompt first, then the conversation
    sent = provider.calls[0]
    assert sent[0].role == "system"
    assert "Headmistress" in sent[0].content
    assert "blood" in sent[0].content  # hard limit in the system prompt
    assert sent[1].content == "What's my task?"
