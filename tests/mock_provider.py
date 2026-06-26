"""Scripted mock LLM provider for tests.

Lets a test enqueue a sequence of "turns". Each call to ``chat_completion``
emits the events for the next turn, so multi-turn tool-use loops can be
driven deterministically without any network access.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from client.providers.base import BaseProvider
from client.response import (
    StreamEvent,
    StreamEventType,
    TextDelta,
    TokenUsage,
    ToolCall,
)


def text_event(content: str) -> StreamEvent:
    return StreamEvent(type=StreamEventType.TEXT_DELTA, text_delta=TextDelta(content))


def tool_event(name: str, arguments: Any, call_id: str = "call-1") -> StreamEvent:
    return StreamEvent(
        type=StreamEventType.TOOL_CALL_COMPLETE,
        tool_call=ToolCall(call_id=call_id, name=name, arguments=arguments),
    )


def done_event(prompt: int = 10, completion: int = 5) -> StreamEvent:
    return StreamEvent(
        type=StreamEventType.MESSAGE_COMPLETE,
        usage=TokenUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        ),
    )


def error_event(message: str) -> StreamEvent:
    return StreamEvent(type=StreamEventType.ERROR, error=message)


class MockProvider(BaseProvider):
    """A provider that replays scripted turns.

    Args:
        turns: a list of turns; each turn is a list of StreamEvent to emit on
               one chat_completion call. When exhausted, emits a final plain
               text turn so loops terminate cleanly.
    """

    def __init__(self, turns: list[list[StreamEvent]] | None = None) -> None:
        super().__init__(api_key="test", model="mock", base_url=None)
        self.turns = turns or []
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> AsyncGenerator[StreamEvent, None]:
        # Record what the agent sent so tests can assert on context state.
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})

        if self.calls and len(self.calls) <= len(self.turns):
            events = self.turns[len(self.calls) - 1]
        else:
            # Default terminal turn: a plain answer with usage.
            events = [text_event("done"), done_event()]

        for event in events:
            yield event

    async def close(self) -> None:
        self.closed = True
