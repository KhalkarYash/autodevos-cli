"""End-to-end agent loop tests with a mock provider (audit Phase 3)."""

import pytest

from agent.events import AgentEventType
from tests.mock_provider import text_event, tool_event, done_event


@pytest.mark.asyncio
async def test_single_text_response(mock_session):
    session, provider = mock_session
    provider.turns = [[text_event("hello back"), done_event()]]

    from agent.agent import Agent

    agent = Agent(session.config)
    agent.session = session

    events = [ev async for ev in agent.run("hi")]
    types = [e.type for e in events]
    assert AgentEventType.AGENT_START in types
    assert AgentEventType.AGENT_END in types
    completes = [e for e in events if e.type == AgentEventType.TEXT_COMPLETE]
    assert completes[-1].data.get("content") == "hello back"


@pytest.mark.asyncio
async def test_multi_turn_tool_use(mock_session, workspace):
    session, provider = mock_session
    (workspace / "f.txt").write_text("file body\n")

    provider.turns = [
        # Turn 1: model calls read_file
        [tool_event("read_file", {"path": "f.txt"}), done_event()],
        # Turn 2: model answers using the tool result
        [text_event("the file says hi"), done_event()],
    ]

    from agent.agent import Agent

    agent = Agent(session.config)
    agent.session = session

    events = [ev async for ev in agent.run("read the file")]
    tool_completes = [e for e in events if e.type == AgentEventType.TOOL_CALL_COMPLETE]
    assert len(tool_completes) == 1
    assert tool_completes[0].data.get("name") == "read_file"

    # The tool result must have been appended to context before turn 2.
    second_call_messages = provider.calls[1]["messages"]
    assert any(m["role"] == "tool" for m in second_call_messages)

    final = [e for e in events if e.type == AgentEventType.TEXT_COMPLETE][-1]
    assert final.data.get("content") == "the file says hi"


@pytest.mark.asyncio
async def test_max_turns_terminates(mock_session):
    session, provider = mock_session
    session.config.max_turns = 2
    # Always return a tool call -> never terminates on its own.
    provider.turns = [
        [tool_event("read_file", {"path": "nope.txt"}, call_id=f"c{i}"), done_event()]
        for i in range(5)
    ]

    from agent.agent import Agent

    agent = Agent(session.config)
    agent.session = session

    events = [ev async for ev in agent.run("loop forever")]
    errors = [e for e in events if e.type == AgentEventType.AGENT_ERROR]
    assert any("Maximum turns" in (e.data.get("error") or "") for e in errors)


@pytest.mark.asyncio
async def test_usage_accumulates(mock_session):
    session, provider = mock_session
    provider.turns = [[text_event("ok"), done_event(prompt=10, completion=5)]]

    from agent.agent import Agent

    agent = Agent(session.config)
    agent.session = session

    async for _ in agent.run("hi"):
        pass
    assert session.context_manager.total_usage.total_tokens == 15
