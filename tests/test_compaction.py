"""ChatCompactor tests (audit C6: non-stream summary collection)."""

import pytest

from context.compaction import ChatCompactor
from context.manager import ContextManager
from tests.mock_provider import text_event, done_event, MockProvider
from client.response import StreamEvent, StreamEventType, TextDelta, TokenUsage


class _SummaryProvider(MockProvider):
    """Emits a summary as a single MESSAGE_COMPLETE carrying text (non-stream path)."""

    async def chat_completion(self, messages, tools=None, stream=True):
        self.calls.append({"stream": stream})
        # Mimic OpenAI non-stream: text arrives with the completion event.
        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            text_delta=TextDelta("COMPACTED SUMMARY"),
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
        )


@pytest.fixture
def cm(config):
    cm = ContextManager(config=config, user_memory=None, tools=[])
    for i in range(5):
        cm.add_user_message(f"message {i}")
        cm.add_assistant_message(f"reply {i}")
    return cm


@pytest.mark.asyncio
async def test_compress_collects_nonstream_summary(config, cm):
    from client.llm_client import LLMClient

    client = LLMClient(config)
    client._provider = _SummaryProvider()
    compactor = ChatCompactor(client)

    summary, usage = await compactor.compress(cm)
    assert summary == "COMPACTED SUMMARY"
    assert usage is not None
    assert usage.total_tokens == 120


@pytest.mark.asyncio
async def test_compress_collects_streamed_summary(config, cm):
    from client.llm_client import LLMClient

    class _Streamed(MockProvider):
        async def chat_completion(self, messages, tools=None, stream=True):
            yield text_event("part1 ")
            yield text_event("part2")
            yield done_event(prompt=50, completion=10)

    client = LLMClient(config)
    client._provider = _Streamed()
    summary, usage = await ChatCompactor(client).compress(cm)
    assert summary == "part1 part2"
    assert usage.total_tokens == 60


@pytest.mark.asyncio
async def test_compress_too_short_returns_none(config):
    from client.llm_client import LLMClient

    cm = ContextManager(config=config, user_memory=None, tools=[])
    cm.add_user_message("only one")
    client = LLMClient(config)
    client._provider = MockProvider()
    summary, usage = await ChatCompactor(client).compress(cm)
    assert summary is None and usage is None
