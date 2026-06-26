"""Shared pytest fixtures.

Isolates every test run from the real user data/config directories via the
AUTODEVOS_DATA_DIR / AUTODEVOS_CONFIG_DIR overrides, and provides helpers for
building Config objects and mock-backed Sessions.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure the project root is importable when pytest is run from anywhere.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Redirect all persistence to a per-test temp directory."""
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    data_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AUTODEVOS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("AUTODEVOS_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("API_KEY", raising=False)
    yield


@pytest.fixture
def workspace(tmp_path):
    """A clean working directory for file-tool tests."""
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture
def make_config(workspace):
    """Factory for Config objects. Defaults to Ollama (no API key required)."""
    from config.config import Config, Provider

    def _make(**overrides):
        config = Config(cwd=workspace)
        config.model.provider = Provider.OLLAMA
        config.model.name = "mock"
        for key, value in overrides.items():
            setattr(config, key, value)
        return config

    return _make


@pytest.fixture
def config(make_config):
    return make_config()


@pytest.fixture
def hook_system(config):
    from hooks.hook_system import HookSystem

    return HookSystem(config)


@pytest.fixture
def approval_manager(config):
    from safety.approval import ApprovalManager

    # YOLO so tool tests don't block on confirmation prompts.
    from config.config import ApprovalPolicy

    return ApprovalManager(ApprovalPolicy.YOLO, config.cwd)


@pytest.fixture
async def mock_session(config, monkeypatch):
    """A fully wired Session with embedded MCP disabled and a mock provider.

    Yields (session, mock_provider). The caller sets mock_provider.turns before
    driving the agent.
    """
    from tools.mcp.mcp_manager import MCPManager
    from agent.session import Session
    from tests.mock_provider import MockProvider

    async def _noop(self):
        return None

    # Skip spinning up the in-process FastMCP servers for unit tests.
    monkeypatch.setattr(MCPManager, "_initialize_embedded_servers", _noop)

    session = Session(config)
    provider = MockProvider()
    session.client._provider = provider
    await session.initialize()

    yield session, provider
