"""Session persistence + checkpoint roundtrip tests (audit Phase 3)."""

import os
import sys
from datetime import datetime

import pytest

from agent.persistence import PersistenceManager, SessionSnapshot
from client.response import TokenUsage


def make_snapshot(session_id="sess-1"):
    return SessionSnapshot(
        session_id=session_id,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 13, 0, 0),
        turn_count=3,
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ],
        total_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def test_save_load_session_roundtrip():
    pm = PersistenceManager()
    snap = make_snapshot()
    pm.save_session(snap)

    loaded = pm.load_session("sess-1")
    assert loaded is not None
    assert loaded.session_id == "sess-1"
    assert loaded.turn_count == 3
    assert loaded.messages == snap.messages
    assert loaded.total_usage.total_tokens == 15
    assert loaded.created_at == snap.created_at


def test_load_missing_session_returns_none():
    pm = PersistenceManager()
    assert pm.load_session("does-not-exist") is None


def test_list_sessions():
    pm = PersistenceManager()
    pm.save_session(make_snapshot("a"))
    pm.save_session(make_snapshot("b"))
    ids = {s["session_id"] for s in pm.list_sessions()}
    assert {"a", "b"} <= ids


def test_checkpoint_roundtrip():
    pm = PersistenceManager()
    snap = make_snapshot("ck")
    cp_id = pm.save_checkpoint(snap)
    assert cp_id

    listed = pm.list_checkpoints()
    assert any(c["id"] == cp_id for c in listed)

    loaded = pm.load_checkpoint(cp_id)
    assert loaded is not None
    assert loaded.messages == snap.messages


def test_load_missing_checkpoint_returns_none():
    pm = PersistenceManager()
    assert pm.load_checkpoint("nope") is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_session_file_permissions_are_owner_only():
    pm = PersistenceManager()
    pm.save_session(make_snapshot("perm"))
    file_path = pm.sessions_dir / "perm.json"
    mode = os.stat(file_path).st_mode & 0o777
    assert mode == 0o600
