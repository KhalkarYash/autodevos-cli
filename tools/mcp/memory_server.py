"""
Memory MCP Server — 3-tier memory (user/project/session) via FastMCP.

Exposes memory as both MCP tools (write operations) and MCP resources
(read operations). The LLM can read memory resources without tool calls,
and write via tool calls.

Tiers:
  - user:    Persists in ~/.local/share/ai-agent/memory.db (global)
  - project: Persists in .ai-agent/memory.db (per-project)
  - session: In-memory dict (ephemeral, dies with session)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from config.loader import get_data_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    key       TEXT PRIMARY KEY,
    value     TEXT NOT NULL,
    tags      TEXT DEFAULT '',
    created   TEXT NOT NULL,
    updated   TEXT NOT NULL
);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_TABLE_SQL)
    conn.commit()
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Migration: import old user_memory.json into SQLite
# ---------------------------------------------------------------------------

def _migrate_json_to_sqlite(json_path: Path, conn: sqlite3.Connection) -> int:
    """Migrate entries from the legacy user_memory.json into the SQLite DB.

    Returns the number of entries migrated.
    """
    if not json_path.exists():
        return 0

    try:
        raw = json_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        entries = data.get("entries", {})
    except Exception:
        logger.warning("Failed to read legacy user_memory.json for migration")
        return 0

    if not entries:
        return 0

    count = 0
    now = _now_iso()
    for key, value in entries.items():
        try:
            conn.execute(
                "INSERT OR IGNORE INTO memories (key, value, tags, created, updated) VALUES (?, ?, ?, ?, ?)",
                (key, str(value), "", now, now),
            )
            count += 1
        except Exception:
            pass

    conn.commit()

    # Rename the old file so migration only runs once
    try:
        backup_path = json_path.with_suffix(".json.migrated")
        json_path.rename(backup_path)
        logger.info(f"Migrated {count} entries from user_memory.json → memory.db")
    except Exception:
        pass

    return count


# ---------------------------------------------------------------------------
# MemoryStore — thin data layer around SQLite + in-memory dicts
# ---------------------------------------------------------------------------

class MemoryStore:
    """Manages the three memory tiers."""

    def __init__(self, project_root: Path | None = None):
        # User-global SQLite
        data_dir = get_data_dir()
        self._user_db_path = data_dir / "memory.db"
        self._user_conn = _connect(self._user_db_path)

        # Run legacy migration once
        legacy_path = data_dir / "user_memory.json"
        _migrate_json_to_sqlite(legacy_path, self._user_conn)

        # Project-scoped SQLite
        self._project_conn: sqlite3.Connection | None = None
        if project_root:
            agent_dir = project_root / ".ai-agent"
            if agent_dir.is_dir() or project_root.exists():
                project_db_path = agent_dir / "memory.db"
                self._project_conn = _connect(project_db_path)

        # Session memory — ephemeral
        self._session: dict[str, dict[str, Any]] = {}

    def _get_conn(self, scope: str) -> sqlite3.Connection | None:
        if scope == "user":
            return self._user_conn
        elif scope == "project":
            return self._project_conn
        return None

    # ── Write ──────────────────────────────────────────────────────────

    def write(
        self,
        key: str,
        value: str,
        scope: str = "user",
        tags: str = "",
    ) -> str:
        if scope == "session":
            self._session[key] = {
                "value": value,
                "tags": tags,
                "created": _now_iso(),
                "updated": _now_iso(),
            }
            return f"Stored in session memory: {key}"

        conn = self._get_conn(scope)
        if conn is None:
            return f"Memory scope '{scope}' is not available (no project context)"

        now = _now_iso()
        conn.execute(
            """INSERT INTO memories (key, value, tags, created, updated)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, tags=excluded.tags, updated=excluded.updated""",
            (key, value, tags, now, now),
        )
        conn.commit()
        return f"Stored in {scope} memory: {key}"

    # ── Read ──────────────────────────────────────────────────────────

    def read(self, key: str, scope: str = "user") -> str | None:
        if scope == "session":
            entry = self._session.get(key)
            return entry["value"] if entry else None

        conn = self._get_conn(scope)
        if conn is None:
            return None

        row = conn.execute("SELECT value FROM memories WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    # ── Search ────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        scope: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        scopes = [scope] if scope else ["session", "project", "user"]

        for s in scopes:
            if s == "session":
                for k, v in self._session.items():
                    if query.lower() in k.lower() or query.lower() in v["value"].lower():
                        results.append({"scope": "session", "key": k, **v})
            else:
                conn = self._get_conn(s)
                if conn is None:
                    continue
                rows = conn.execute(
                    "SELECT key, value, tags, created, updated FROM memories WHERE key LIKE ? OR value LIKE ? LIMIT ?",
                    (f"%{query}%", f"%{query}%", limit),
                ).fetchall()
                for row in rows:
                    results.append({
                        "scope": s,
                        "key": row["key"],
                        "value": row["value"],
                        "tags": row["tags"],
                        "created": row["created"],
                        "updated": row["updated"],
                    })

            if len(results) >= limit:
                break

        return results[:limit]

    # ── Delete ────────────────────────────────────────────────────────

    def delete(self, key: str, scope: str = "user") -> str:
        if scope == "session":
            if key in self._session:
                del self._session[key]
                return f"Deleted from session memory: {key}"
            return f"Key not found in session memory: {key}"

        conn = self._get_conn(scope)
        if conn is None:
            return f"Memory scope '{scope}' is not available"

        cursor = conn.execute("DELETE FROM memories WHERE key = ?", (key,))
        conn.commit()
        if cursor.rowcount > 0:
            return f"Deleted from {scope} memory: {key}"
        return f"Key not found in {scope} memory: {key}"

    # ── List ──────────────────────────────────────────────────────────

    def list_all(self, scope: str = "user") -> list[dict[str, Any]]:
        if scope == "session":
            return [
                {"key": k, "value": v["value"], "tags": v["tags"]}
                for k, v in self._session.items()
            ]

        conn = self._get_conn(scope)
        if conn is None:
            return []

        rows = conn.execute("SELECT key, value, tags FROM memories").fetchall()
        return [{"key": r["key"], "value": r["value"], "tags": r["tags"]} for r in rows]

    # ── Bulk read (for resource injection) ────────────────────────────

    def get_all_formatted(self, scope: str) -> str:
        entries = self.list_all(scope)
        if not entries:
            return f"No {scope} memories stored."

        lines = [f"{scope.title()} memories ({len(entries)} entries):"]
        for e in entries:
            tag_str = f" [{e['tags']}]" if e.get("tags") else ""
            lines.append(f"  - {e['key']}: {e['value']}{tag_str}")
        return "\n".join(lines)

    def close(self) -> None:
        try:
            self._user_conn.close()
        except Exception:
            pass
        if self._project_conn:
            try:
                self._project_conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# create_memory_server — builds the FastMCP server instance
# ---------------------------------------------------------------------------

def create_memory_server(project_root: Path | None = None) -> FastMCP:
    """Create a FastMCP Memory Server with tools + resources.

    Args:
        project_root: Path to the project root (for project-scoped memory).
                      If None, project memory is unavailable.

    Returns:
        A configured FastMCP server instance.
    """
    mcp = FastMCP("autodevos-memory")
    store = MemoryStore(project_root)

    # ── Tools ─────────────────────────────────────────────────────────

    @mcp.tool("mem_write")
    def mem_write(
        key: str,
        value: str,
        scope: str = "user",
        tags: str = "",
    ) -> str:
        """Store a memory entry.

        Args:
            key: Unique key for this memory entry.
            value: The content to remember.
            scope: Memory tier — 'user' (global), 'project' (per-project), or 'session' (ephemeral).
            tags: Optional comma-separated tags for categorization.
        """
        return store.write(key, value, scope, tags)

    @mcp.tool("mem_read")
    def mem_read(key: str, scope: str = "user") -> str:
        """Read a specific memory entry by key.

        Args:
            key: The memory key to look up.
            scope: Memory tier to search — 'user', 'project', or 'session'.
        """
        result = store.read(key, scope)
        if result is None:
            return f"Memory not found: {key} (scope: {scope})"
        return f"{key}: {result}"

    @mcp.tool("mem_search")
    def mem_search(
        query: str,
        scope: str | None = None,
        limit: int = 20,
    ) -> str:
        """Search memory entries by keyword.

        Searches across key names and values. Use scope=None to search all tiers.

        Args:
            query: Search term to find in keys and values.
            scope: Optional scope to limit search — 'user', 'project', 'session', or None for all.
            limit: Maximum number of results to return.
        """
        results = store.search(query, scope, limit)
        if not results:
            return f"No memories found matching: {query}"

        lines = [f"Found {len(results)} memories matching '{query}':"]
        for r in results:
            lines.append(f"  [{r['scope']}] {r['key']}: {r['value']}")
        return "\n".join(lines)

    @mcp.tool("mem_delete")
    def mem_delete(key: str, scope: str = "user") -> str:
        """Delete a memory entry.

        Args:
            key: The memory key to delete.
            scope: Memory tier — 'user', 'project', or 'session'.
        """
        return store.delete(key, scope)

    @mcp.tool("mem_list")
    def mem_list(scope: str = "user") -> str:
        """List all memory entries in a scope.

        Args:
            scope: Memory tier — 'user', 'project', or 'session'.
        """
        entries = store.list_all(scope)
        if not entries:
            return f"No {scope} memories stored."

        lines = [f"{scope.title()} memories ({len(entries)} entries):"]
        for e in entries:
            tag_str = f" [{e['tags']}]" if e.get("tags") else ""
            lines.append(f"  - {e['key']}: {e['value']}{tag_str}")
        return "\n".join(lines)

    # ── Resources ─────────────────────────────────────────────────────

    @mcp.resource("mem://user")
    def mem_user_resource() -> str:
        """All user-global memories. Injected into every session."""
        return store.get_all_formatted("user")

    @mcp.resource("mem://project")
    def mem_project_resource() -> str:
        """Project-scoped memories. Injected when working in this project."""
        return store.get_all_formatted("project")

    @mcp.resource("mem://session")
    def mem_session_resource() -> str:
        """Current session memories. Reset when session ends."""
        return store.get_all_formatted("session")

    # Attach store to server for cleanup
    mcp._memory_store = store  # type: ignore[attr-defined]

    return mcp
