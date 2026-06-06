from sqlalchemy import text


async def test_session_executes_select_one(session):
    result = await session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1
