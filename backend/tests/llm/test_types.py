from app.llm.types import ChatMessage, ChatResult, ToolCall


def test_chat_result_defaults_to_no_tool_calls():
    r = ChatResult(content="hi")
    assert r.content == "hi"
    assert r.tool_calls == []


def test_tool_call_fields():
    tc = ToolCall(id="1", name="assign_task", arguments='{"x": 1}')
    assert tc.name == "assign_task"


def test_chat_message_role_content():
    m = ChatMessage(role="user", content="ping")
    assert m.role == "user"
