from sqlalchemy import select

from app.db.models.message import Message
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


async def test_message_persists_role_and_content(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    session.add(Message(profile_id=p.id, role="user", content="hello"))
    session.add(Message(profile_id=p.id, role="assistant", content="kneel."))
    await session.flush()
    rows = (await session.execute(
        select(Message).where(Message.profile_id == p.id).order_by(Message.created_at)
    )).scalars().all()
    assert [m.role for m in rows] == ["user", "assistant"]
    assert rows[1].content == "kneel."


async def test_message_stores_action_json(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    m = Message(
        profile_id=p.id,
        role="assistant",
        content="On the board.",
        action={"tool": "assign_task", "description": "Posture drill"},
    )
    session.add(m)
    await session.flush()
    await session.refresh(m)
    assert m.action["tool"] == "assign_task"
