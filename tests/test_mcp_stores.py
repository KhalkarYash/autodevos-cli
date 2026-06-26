"""Memory + Context MCP store tests (the embedded server data layers)."""

import pytest

from context.manager import ContextManager
from tools.mcp.memory_server import MemoryStore
from tools.mcp.context_server import ContextStore


# ── MemoryStore ────────────────────────────────────────────────────────────

@pytest.fixture
def store(workspace):
    s = MemoryStore(project_root=workspace)
    yield s
    s.close()


def test_user_write_read(store):
    store.write("k1", "v1", scope="user")
    assert store.read("k1", scope="user") == "v1"


def test_read_missing_returns_none(store):
    assert store.read("absent", scope="user") is None


def test_write_upsert(store):
    store.write("k", "old", scope="user")
    store.write("k", "new", scope="user")
    assert store.read("k", scope="user") == "new"


def test_session_scope_ephemeral(store):
    store.write("s", "sv", scope="session")
    assert store.read("s", scope="session") == "sv"
    # session not in sqlite tiers
    assert store.read("s", scope="user") is None


def test_project_scope(store):
    store.write("p", "pv", scope="project")
    assert store.read("p", scope="project") == "pv"


def test_search_across_tiers(store):
    store.write("alpha", "find-me", scope="user")
    store.write("beta", "other", scope="session")
    hits = store.search("find-me")
    assert any(h["key"] == "alpha" for h in hits)


def test_delete(store):
    store.write("d", "x", scope="user")
    msg = store.delete("d", scope="user")
    assert "Deleted" in msg
    assert store.read("d", scope="user") is None


def test_list_and_formatted(store):
    store.write("a", "1", scope="user")
    store.write("b", "2", scope="user")
    keys = {e["key"] for e in store.list_all("user")}
    assert {"a", "b"} <= keys
    formatted = store.get_all_formatted("user")
    assert "a" in formatted and "b" in formatted


# ── ContextStore ───────────────────────────────────────────────────────────

@pytest.fixture
def bound_ctx(config):
    cm = ContextManager(config=config, user_memory=None, tools=[])
    store = ContextStore()
    store.bind_context_manager(cm)
    return store, cm


def test_context_not_bound_safe_defaults():
    store = ContextStore()
    assert store.is_bound is False
    assert store.get_messages() == []
    assert store.get_message_count() == 0


def test_context_checkpoint_and_rollback(bound_ctx):
    store, cm = bound_ctx
    cm.add_user_message("first")
    cp = store.create_checkpoint("before")
    assert cp.startswith("ctx-ckpt-")

    cm.add_user_message("second")
    assert cm.message_count == 2

    result = store.rollback(cp)
    assert "Restored" in result
    assert cm.message_count == 1
    assert cm.get_messages()[-1]["content"] == "first"


def test_context_rollback_missing(bound_ctx):
    store, _ = bound_ctx
    assert "not found" in store.rollback("ctx-ckpt-999")


def test_context_usage_report(bound_ctx):
    store, cm = bound_ctx
    cm.add_user_message("hello")
    usage = store.get_usage()
    assert usage["message_count"] == 1
    assert "context_window" in usage


def test_context_list_checkpoints(bound_ctx):
    store, cm = bound_ctx
    cm.add_user_message("x")
    store.create_checkpoint("one")
    store.create_checkpoint("two")
    assert len(store.list_checkpoints()) == 2
