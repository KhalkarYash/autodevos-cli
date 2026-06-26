"""Builtin tool + registry tests (audit Phase 5, M4 path traversal)."""

import pytest

from pathlib import Path

from tools.base import ToolInvocation
from tools.builtin.edit_file import EditTool
from tools.builtin.read_file import ReadFileTool
from tools.builtin.write_file import WriteFileTool
from tools.builtin.shell import ShellTool
from tools.builtin.list_dir import ListDirTool
from tools.builtin.glob import GlobTool
from tools.builtin.grep import GrepTool
from tools.registry import create_default_registry
from utils.paths import resolve_path


def invoke(params, workspace):
    return ToolInvocation(params=params, cwd=workspace)


# ── Path safety ────────────────────────────────────────────────────────────

def test_resolve_path_blocks_traversal(workspace):
    with pytest.raises(ValueError):
        resolve_path(workspace, "../../etc/passwd")


def test_resolve_path_allows_within(workspace):
    p = resolve_path(workspace, "sub/file.txt")
    assert str(p).startswith(str(workspace.resolve()))


# ── write / read / edit ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_write_then_read(config, workspace):
    wt = WriteFileTool(config)
    res = await wt.execute(invoke({"path": "f.txt", "content": "hello\n"}, workspace))
    assert res.success
    assert (workspace / "f.txt").read_text() == "hello\n"

    rt = ReadFileTool(config)
    res = await rt.execute(invoke({"path": "f.txt"}, workspace))
    assert res.success
    assert "hello" in res.output


@pytest.mark.asyncio
async def test_edit_replaces_text(config, workspace):
    (workspace / "f.txt").write_text("foo bar\n")
    et = EditTool(config)
    res = await et.execute(invoke({"path": "f.txt", "old_string": "foo", "new_string": "baz"}, workspace))
    assert res.success
    assert (workspace / "f.txt").read_text() == "baz bar\n"


@pytest.mark.asyncio
async def test_edit_ambiguous_without_replace_all(config, workspace):
    (workspace / "f.txt").write_text("a a a\n")
    et = EditTool(config)
    res = await et.execute(invoke({"path": "f.txt", "old_string": "a", "new_string": "b"}, workspace))
    assert not res.success


# ── glob / grep / list_dir ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_glob_finds_files(config, workspace):
    (workspace / "x.py").write_text("")
    (workspace / "y.txt").write_text("")
    res = await GlobTool(config).execute(invoke({"pattern": "*.py"}, workspace))
    assert res.success
    assert "x.py" in res.output


@pytest.mark.asyncio
async def test_grep_matches(config, workspace):
    (workspace / "code.py").write_text("def target():\n    pass\n")
    res = await GrepTool(config).execute(invoke({"pattern": "target"}, workspace))
    assert res.success
    assert "target" in res.output


@pytest.mark.asyncio
async def test_list_dir(config, workspace):
    (workspace / "a").mkdir()
    (workspace / "b.txt").write_text("")
    res = await ListDirTool(config).execute(invoke({"path": "."}, workspace))
    assert res.success
    assert "b.txt" in res.output


# ── shell security ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_shell_blocks_dangerous(config, workspace):
    res = await ShellTool(config).execute(invoke({"command": "rm -rf /"}, workspace))
    assert not res.success
    assert res.metadata.get("blocked") is True


@pytest.mark.asyncio
async def test_shell_runs_safe_command(config, workspace):
    res = await ShellTool(config).execute(invoke({"command": "echo hi"}, workspace))
    assert res.success
    assert "hi" in res.output


@pytest.mark.asyncio
async def test_shell_timeout(config, workspace):
    res = await ShellTool(config).execute(invoke({"command": "sleep 5", "timeout": 1}, workspace))
    assert not res.success
    assert "timed out" in res.error.lower() or "timed out" in res.output.lower()


def test_shell_uses_login_shell(monkeypatch):
    monkeypatch.setattr("tools.builtin.shell.sys.platform", "darwin")
    monkeypatch.setenv("SHELL", "/bin/zsh")
    cmd = ShellTool.__new__(ShellTool)
    assert cmd._get_shell_command("npm test") == ["/bin/zsh", "-lc", "npm test"]


def test_shell_resolves_nvm_node_bin(tmp_path):
    nvm_dir = tmp_path / ".nvm"
    (nvm_dir / "alias").mkdir(parents=True)
    (nvm_dir / "alias" / "default").write_text("22")
    node_bin = nvm_dir / "versions" / "node" / "v22.18.0" / "bin"
    node_bin.mkdir(parents=True)

    resolved = ShellTool._resolve_nvm_node_bin(tmp_path)
    assert resolved == node_bin


def test_shell_augment_path_includes_nvm(config, monkeypatch, tmp_path):
    home = str(tmp_path)
    nvm_dir = Path(home) / ".nvm"
    (nvm_dir / "alias").mkdir(parents=True)
    (nvm_dir / "alias" / "default").write_text("22")
    node_bin = nvm_dir / "versions" / "node" / "v22.18.0" / "bin"
    node_bin.mkdir(parents=True)

    monkeypatch.setenv("HOME", home)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    env = ShellTool(config)._build_environment()
    assert str(node_bin) in env["PATH"].split(":")


# ── registry invoke error paths (audit C3) ────────────────────────────────

@pytest.mark.asyncio
async def test_registry_unknown_tool(config, workspace, hook_system):
    reg = create_default_registry(config)
    res = await reg.invoke("nope", {}, workspace, hook_system)
    assert not res.success
    assert res.metadata.get("tool_name") == "nope"


@pytest.mark.asyncio
async def test_registry_invalid_params(config, workspace, hook_system):
    reg = create_default_registry(config)
    res = await reg.invoke("read_file", {}, workspace, hook_system)
    assert not res.success
    assert "validation_errors" in res.metadata


@pytest.mark.asyncio
async def test_registry_invoke_success(config, workspace, hook_system, approval_manager):
    (workspace / "f.txt").write_text("data\n")
    reg = create_default_registry(config)
    res = await reg.invoke("read_file", {"path": "f.txt"}, workspace, hook_system, approval_manager)
    assert res.success
    assert "data" in res.output


def test_default_registry_includes_apply_patch(config):
    reg = create_default_registry(config)
    assert reg.get("apply_patch") is not None
