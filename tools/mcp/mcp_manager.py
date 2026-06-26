import asyncio
import logging
from pathlib import Path
from typing import Any

from config.config import Config
from tools.mcp.client import EmbeddedMCPClient, MCPClient, MCPServerStatus
from tools.mcp.mcp_tool import MCPTool
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class MCPManager:
    def __init__(self, config: Config):
        self.config = config
        self._clients: dict[str, MCPClient] = {}
        self._embedded_clients: dict[str, EmbeddedMCPClient] = {}
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        # ── 1. Initialize embedded MCP servers (Memory + Context) ─────
        await self._initialize_embedded_servers()

        # ── 2. Initialize external user-configured MCP servers ────────
        mcp_configs = self.config.mcp_servers

        if mcp_configs:
            for name, server_config in mcp_configs.items():
                if not server_config.enabled:
                    continue

                self._clients[name] = MCPClient(
                    name=name,
                    config=server_config,
                    cwd=self.config.cwd,
                )

            connection_tasks = [
                asyncio.wait_for(
                    client.connect(),
                    timeout=client.config.startup_timeout_sec,
                )
                for name, client in self._clients.items()
            ]

            await asyncio.gather(*connection_tasks, return_exceptions=True)

        self._initialized = True

    async def _initialize_embedded_servers(self) -> None:
        """Create and connect to the builtin Memory + Context MCP servers."""
        from tools.mcp.memory_server import create_memory_server
        from tools.mcp.context_server import create_context_server

        # Memory server (with project-scoped memory if in a project)
        memory_server = create_memory_server(project_root=self.config.cwd)
        memory_client = EmbeddedMCPClient("memory", memory_server)
        try:
            await memory_client.connect()
            self._embedded_clients["memory"] = memory_client
            logger.info("Memory MCP server initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Memory MCP server: {e}")

        # Context server
        context_server = create_context_server()
        context_client = EmbeddedMCPClient("context", context_server)
        try:
            await context_client.connect()
            self._embedded_clients["context"] = context_client
            logger.info("Context MCP server initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Context MCP server: {e}")

    def get_embedded_client(self, name: str) -> EmbeddedMCPClient | None:
        """Get an embedded MCP client by name (e.g., 'memory', 'context')."""
        return self._embedded_clients.get(name)

    def get_context_store(self):
        """Get the ContextStore from the embedded context server."""
        client = self._embedded_clients.get("context")
        if client and hasattr(client, "_server"):
            return getattr(client._server, "_context_store", None)
        return None

    def get_memory_store(self):
        """Get the MemoryStore from the embedded memory server."""
        client = self._embedded_clients.get("memory")
        if client and hasattr(client, "_server"):
            return getattr(client._server, "_memory_store", None)
        return None

    def register_tools(self, registry: ToolRegistry) -> int:
        count = 0

        # Register embedded server tools (memory, context)
        for client in self._embedded_clients.values():
            if client.status != MCPServerStatus.CONNECTED:
                continue

            for tool_info in client.tools:
                mcp_tool = MCPTool(
                    tool_info=tool_info,
                    client=client,
                    config=self.config,
                    name=tool_info.name,  # No prefix for builtin servers
                )
                registry.register_mcp_tool(mcp_tool)
                count += 1

        # Register external server tools (user-configured)
        for client in self._clients.values():
            if client.status != MCPServerStatus.CONNECTED:
                continue

            for tool_info in client.tools:
                mcp_tool = MCPTool(
                    tool_info=tool_info,
                    client=client,
                    config=self.config,
                    name=f"{client.name}__{tool_info.name}",
                )
                registry.register_mcp_tool(mcp_tool)
                count += 1

        return count

    async def read_resource(self, uri: str) -> str | None:
        """Read an MCP resource by URI from any connected server.

        Tries embedded servers first, then external servers.
        Returns the text content, or None if not found.
        """
        # Try embedded servers first
        for client in self._embedded_clients.values():
            if client.status != MCPServerStatus.CONNECTED:
                continue
            try:
                resources = await client.list_resources()
                resource_uris = {r["uri"] for r in resources}
                if uri in resource_uris:
                    return await client.read_resource(uri)
            except Exception:
                continue

        # Then external servers
        for client in self._clients.values():
            if client.status != MCPServerStatus.CONNECTED:
                continue
            try:
                resources = await client.list_resources()
                resource_uris = {r["uri"] for r in resources}
                if uri in resource_uris:
                    return await client.read_resource(uri)
            except Exception:
                continue

        return None

    async def shutdown(self) -> None:
        # Shut down embedded servers
        embedded_tasks = [
            client.disconnect() for client in self._embedded_clients.values()
        ]
        await asyncio.gather(*embedded_tasks, return_exceptions=True)

        # Clean up memory store
        for client in self._embedded_clients.values():
            if hasattr(client, "_server"):
                store = getattr(client._server, "_memory_store", None)
                if store and hasattr(store, "close"):
                    store.close()

        self._embedded_clients.clear()

        # Shut down external servers
        disconnection_tasks = [client.disconnect() for client in self._clients.values()]
        await asyncio.gather(*disconnection_tasks, return_exceptions=True)
        self._clients.clear()

        self._initialized = False

    def get_all_servers(self) -> list[dict[str, Any]]:
        servers = []

        # Embedded servers
        for name, client in self._embedded_clients.items():
            resources = []  # Can't list synchronously, but we know our URIs
            server_info = {
                "name": f"[builtin] {name}",
                "status": client.status.value,
                "tools": len(client.tools),
                "type": "embedded",
            }
            servers.append(server_info)

        # External servers
        for name, client in self._clients.items():
            server_info = {
                "name": name,
                "status": client.status.value,
                "tools": len(client.tools),
                "type": "external",
            }
            servers.append(server_info)

        return servers

    def get_server_statuses(self) -> dict[str, Any]:
        return {server["name"]: server for server in self.get_all_servers()}

