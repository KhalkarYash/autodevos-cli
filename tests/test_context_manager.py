"""ContextManager tests (audit Phase 4: prune, compression, summary, load)."""

import pytest

from client.response import TokenUsage
from context.manager import ContextManager


@pytest.fixture
def cm(config):
    return ContextManager(config=config, user_memory=None, tools=[])


def test_get_messages_includes_system_prompt(cm):
    cm.add_user_message("hello")
    messages = cm.get_messages()
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "hello"}


def test_message_count_excludes_system(cm):
    cm.add_user_message("a")
    cm.add_assistant_message("b")
    assert cm.message_count == 2


def test_assistant_tool_calls_serialized(cm):
    cm.add_assistant_message(
        "calling",
        tool_calls=[{"id": "1", "type": "function", "function": {"name": "x", "arguments": "{}"}}],
    )
    msg = cm.get_messages()[-1]
    assert msg["tool_calls"][0]["function"]["name"] == "x"


def test_tool_result_wrapped_untrusted(cm):
    cm.add_tool_result("call-1", "secret output")
    msg = cm.get_messages()[-1]
    assert msg["role"] == "tool"
    assert 'trusted="false"' in msg["content"]
    assert "secret output" in msg["content"]


def test_needs_compression_threshold(cm):
    assert cm.needs_compression() is False
    cm.set_latest_usage(TokenUsage(total_tokens=int(cm.config.model.context_window * 0.9)))
    assert cm.needs_compression() is True


def test_clear_removes_messages(cm):
    cm.add_user_message("a")
    cm.clear()
    assert cm.message_count == 0


def test_load_messages_drops_system(cm):
    cm.load_messages([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo"},
    ])
    assert cm.message_count == 2
    assert cm.get_messages()[1]["content"] == "hi"


def test_replace_with_summary_resets_to_continuation(cm):
    for i in range(5):
        cm.add_user_message(f"msg {i}")
    cm.replace_with_summary("SUMMARY OF WORK")
    msgs = [m for m in cm.get_messages() if m["role"] != "system"]
    # continuation user + ack assistant + continue user
    assert len(msgs) == 3
    assert "SUMMARY OF WORK" in msgs[0]["content"]
    assert msgs[1]["role"] == "assistant"


def test_prune_tool_outputs_clears_large_old_results(cm):
    cm.add_user_message("first")
    # Big tool outputs exceeding the protect threshold. Use varied tokens so
    # BPE doesn't collapse them — each result is ~2000 tokens.
    big = " ".join(str(n) for n in range(2000))
    for i in range(60):
        cm.add_tool_result(f"call-{i}", big)
    cm.add_user_message("second")  # need >=2 user messages to prune
    pruned = cm.prune_tool_outputs()
    assert pruned > 0
    cleared = [m for m in cm.get_messages() if m.get("content") == "[Old tool result content cleared]"]
    assert len(cleared) == pruned


def test_prune_noop_with_single_user_message(cm):
    cm.add_user_message("only")
    cm.add_tool_result("c", "x" * 5000)
    assert cm.prune_tool_outputs() == 0
