"""
Context MCP Server — Externalized conversation context via FastMCP.

Wraps the existing ContextManager and exposes it as MCP tools + resources.
The agent uses tools to push messages and manage checkpoints, while resources
provide read-only access to current state (messages, usage, checkpoints).

This server does NOT replace ContextManager — it wraps it, providing MCP
access to context state while keeping the proven ContextManager engine.
"""

from __future__ import annotations

import json
import copy
import logging
from datetime import datetime, timezone
from typing import Any

from fastmcp import FastMCP

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Checkpoint store — in-memory snapshots of context state
# ---------------------------------------------------------------------------

class ContextCheckpoint:
    """A snapshot of context state at a point in time."""

    def __init__(
        self,
        checkpoint_id: str,
        label: str,
        messages: list[dict[str, Any]],
        timestamp: str,
    ):
        self.checkpoint_id = checkpoint_id
        self.label = label
        self.messages = messages
        self.timestamp = timestamp


class ContextStore:
    """Manages context state externally for MCP access.

    This wraps a reference to the live ContextManager so that
    MCP resources always reflect the current state.
    """

    def __init__(self) -> None:
        self._context_manager = None  # Set after session init
        self._checkpoints: dict[str, ContextCheckpoint] = {}
        self._checkpoint_counter = 0

    def bind_context_manager(self, context_manager) -> None:
        """Bind to the live ContextManager instance."""
        self._context_manager = context_manager

    @property
    def is_bound(self) -> bool:
        return self._context_manager is not None

    # ── Message access ────────────────────────────────────────────────

    def get_messages(self) -> list[dict[str, Any]]:
        if not self.is_bound:
            return []
        return self._context_manager.get_messages()

    def get_message_count(self) -> int:
        if not self.is_bound:
            return 0
        return self._context_manager.message_count

    # ── Usage stats ───────────────────────────────────────────────────

    def get_usage(self) -> dict[str, Any]:
        if not self.is_bound:
            return {"status": "not initialized"}

        cm = self._context_manager
        return {
            "message_count": cm.message_count,
            "total_usage": {
                "prompt_tokens": cm.total_usage.prompt_tokens,
                "completion_tokens": cm.total_usage.completion_tokens,
                "total_tokens": cm.total_usage.total_tokens,
                "cached_tokens": cm.total_usage.cached_tokens,
            },
            "needs_compression": cm.needs_compression(),
            "context_window": cm.config.model.context_window,
        }

    # ── Checkpoints ───────────────────────────────────────────────────

    def create_checkpoint(self, label: str | None = None) -> str:
        if not self.is_bound:
            return "Context not initialized"

        self._checkpoint_counter += 1
        checkpoint_id = f"ctx-ckpt-{self._checkpoint_counter}"
        lbl = label or f"Checkpoint {self._checkpoint_counter}"

        messages = copy.deepcopy(self._context_manager.get_messages())
        self._checkpoints[checkpoint_id] = ContextCheckpoint(
            checkpoint_id=checkpoint_id,
            label=lbl,
            messages=messages,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        return checkpoint_id

    def rollback(self, checkpoint_id: str) -> str:
        if not self.is_bound:
            return "Context not initialized"

        ckpt = self._checkpoints.get(checkpoint_id)
        if ckpt is None:
            return f"Checkpoint not found: {checkpoint_id}"

        self._context_manager.load_messages(copy.deepcopy(ckpt.messages))
        return f"Restored context to checkpoint: {ckpt.label} ({checkpoint_id})"

    def list_checkpoints(self) -> list[dict[str, Any]]:
        return [
            {
                "id": c.checkpoint_id,
                "label": c.label,
                "message_count": len(c.messages),
                "timestamp": c.timestamp,
            }
            for c in self._checkpoints.values()
        ]

    def clear(self) -> str:
        if not self.is_bound:
            return "Context not initialized"
        self._context_manager.clear()
        return "Context cleared"


# ---------------------------------------------------------------------------
# create_context_server — builds the FastMCP server instance
# ---------------------------------------------------------------------------

def create_context_server() -> FastMCP:
    """Create a FastMCP Context Server with tools + resources.

    Returns:
        A configured FastMCP server instance.
    """
    mcp = FastMCP("autodevos-context")
    store = ContextStore()

    # ── Tools ─────────────────────────────────────────────────────────

    @mcp.tool("ctx_checkpoint")
    def ctx_checkpoint(label: str = "") -> str:
        """Create a snapshot of the current conversation context.

        Use this to save a restore point before making significant changes
        or exploring a different approach.

        Args:
            label: Optional human-readable label for this checkpoint.
        """
        checkpoint_id = store.create_checkpoint(label or None)
        return f"Checkpoint created: {checkpoint_id}"

    @mcp.tool("ctx_rollback")
    def ctx_rollback(checkpoint_id: str) -> str:
        """Restore conversation context to a previous checkpoint.

        This reverts the message history to the state captured at the given
        checkpoint. Use this to undo changes or restart from a known-good state.

        Args:
            checkpoint_id: The checkpoint ID to restore (from ctx_checkpoint).
        """
        return store.rollback(checkpoint_id)

    @mcp.tool("ctx_clear")
    def ctx_clear() -> str:
        """Clear all conversation context.

        This removes all messages from the conversation history.
        The system prompt is preserved.
        """
        return store.clear()

    @mcp.tool("ctx_summary")
    def ctx_summary() -> str:
        """Get a summary of current context state.

        Returns message count, token usage, compression status, and
        available checkpoints.
        """
        usage = store.get_usage()
        checkpoints = store.list_checkpoints()

        lines = ["Context Summary:"]
        lines.append(f"  Messages: {usage.get('message_count', 0)}")

        total = usage.get("total_usage", {})
        lines.append(f"  Prompt tokens: {total.get('prompt_tokens', 0)}")
        lines.append(f"  Completion tokens: {total.get('completion_tokens', 0)}")
        lines.append(f"  Total tokens: {total.get('total_tokens', 0)}")
        lines.append(f"  Cached tokens: {total.get('cached_tokens', 0)}")
        lines.append(f"  Needs compression: {usage.get('needs_compression', False)}")
        lines.append(f"  Context window: {usage.get('context_window', 'N/A')}")
        lines.append(f"  Checkpoints: {len(checkpoints)}")

        if checkpoints:
            for c in checkpoints:
                lines.append(f"    - {c['id']}: {c['label']} ({c['message_count']} msgs, {c['timestamp']})")

        return "\n".join(lines)

    # ── Resources ─────────────────────────────────────────────────────

    @mcp.resource("ctx://current")
    def ctx_current_resource() -> str:
        """Current conversation messages as JSON.

        This resource contains the full message history in the format
        expected by the LLM API (role, content, tool_calls, etc.).
        """
        messages = store.get_messages()
        return json.dumps(messages, indent=2, ensure_ascii=False)

    @mcp.resource("ctx://usage")
    def ctx_usage_resource() -> str:
        """Current token usage and context stats.

        Includes message count, token usage breakdown, compression status,
        and context window size.
        """
        usage = store.get_usage()
        return json.dumps(usage, indent=2, ensure_ascii=False)

    @mcp.resource("ctx://checkpoints")
    def ctx_checkpoints_resource() -> str:
        """List of available context checkpoints.

        Each checkpoint includes its ID, label, message count, and timestamp.
        """
        checkpoints = store.list_checkpoints()
        return json.dumps(checkpoints, indent=2, ensure_ascii=False)

    # Attach store to server for binding later
    mcp._context_store = store  # type: ignore[attr-defined]

    return mcp
