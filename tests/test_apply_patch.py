"""apply_patch tool tests (atomic multi-file edits)."""

import pytest

from tools.base import ToolInvocation
from tools.builtin.apply_patch import ApplyPatchTool


@pytest.fixture
def tool(config):
    return ApplyPatchTool(config)


def inv(workspace, edits):
    return ToolInvocation(params={"edits": edits}, cwd=workspace)


@pytest.mark.asyncio
async def test_multi_file_create_and_edit(tool, workspace):
    (workspace / "a.txt").write_text("hello world\nfoo\n")
    res = await tool.execute(inv(workspace, [
        {"path": "a.txt", "old_string": "hello", "new_string": "HI"},
        {"path": "b.txt", "old_string": "", "new_string": "new file\n"},
    ]))
    assert res.success
    assert (workspace / "a.txt").read_text() == "HI world\nfoo\n"
    assert (workspace / "b.txt").read_text() == "new file\n"
    assert res.metadata["created"] == 1
    assert res.metadata["modified"] == 1


@pytest.mark.asyncio
async def test_chained_edits_same_file(tool, workspace):
    (workspace / "a.txt").write_text("one two three\n")
    res = await tool.execute(inv(workspace, [
        {"path": "a.txt", "old_string": "one", "new_string": "1"},
        {"path": "a.txt", "old_string": "three", "new_string": "3"},
    ]))
    assert res.success
    assert (workspace / "a.txt").read_text() == "1 two 3\n"


@pytest.mark.asyncio
async def test_ambiguous_match_aborts_atomically(tool, workspace):
    (workspace / "a.txt").write_text("x x x\n")
    res = await tool.execute(inv(workspace, [
        {"path": "a.txt", "old_string": "x", "new_string": "Y"},
        {"path": "b.txt", "old_string": "", "new_string": "should not exist\n"},
    ]))
    assert not res.success
    assert "found 3 times" in res.error
    # Atomicity: neither file changed.
    assert (workspace / "a.txt").read_text() == "x x x\n"
    assert not (workspace / "b.txt").exists()


@pytest.mark.asyncio
async def test_replace_all(tool, workspace):
    (workspace / "a.txt").write_text("a a a\n")
    res = await tool.execute(inv(workspace, [
        {"path": "a.txt", "old_string": "a", "new_string": "b", "replace_all": True},
    ]))
    assert res.success
    assert (workspace / "a.txt").read_text() == "b b b\n"


@pytest.mark.asyncio
async def test_missing_old_string_on_existing_file_errors(tool, workspace):
    (workspace / "a.txt").write_text("content\n")
    res = await tool.execute(inv(workspace, [
        {"path": "a.txt", "old_string": "", "new_string": "x"},
    ]))
    assert not res.success


@pytest.mark.asyncio
async def test_noop_returns_error(tool, workspace):
    (workspace / "a.txt").write_text("same\n")
    res = await tool.execute(inv(workspace, [
        {"path": "a.txt", "old_string": "same", "new_string": "same"},
    ]))
    assert not res.success


@pytest.mark.asyncio
async def test_confirmation_lists_affected_paths(tool, workspace):
    (workspace / "a.txt").write_text("hello\n")
    conf = await tool.get_confirmation(inv(workspace, [
        {"path": "a.txt", "old_string": "hello", "new_string": "bye"},
        {"path": "b.txt", "old_string": "", "new_string": "x\n"},
    ]))
    names = {p.name for p in conf.affected_paths}
    assert names == {"a.txt", "b.txt"}
    assert conf.diff is not None
    assert "bye" in conf.diff.to_diff()


@pytest.mark.asyncio
async def test_path_traversal_blocked(tool, workspace):
    res = await tool.execute(inv(workspace, [
        {"path": "../escape.txt", "old_string": "", "new_string": "pwn"},
    ]))
    assert not res.success
