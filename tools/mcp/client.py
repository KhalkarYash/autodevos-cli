from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
from typing import Any, TYPE_CHECKING

from config.config import MCPServerConfig
from fastmcp import Client
from fastmcp.client.transports import SSETransport, StdioTransport

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)


class MCPServerStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MCPToolInfo:

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


class MCPClient:
    def __init__(
        self,
        name: str,
        config: MCPServerConfig,
        cwd: Path,
    ) -> None:
        self.name = name
        self.config = config
        self.cwd = cwd
        self.status = MCPServerStatus.DISCONNECTED
        self._client: Client | None = None

        self._tools: dict[str, MCPToolInfo] = dict()

    @property
    def tools(self) -> list[MCPToolInfo]:
        return list(self._tools.values())

    def _create_transport(self) -> StdioTransport | SSETransport:
        if self.config.command:
            env = os.environ.copy()
            env.update(self.config.env)

            return StdioTransport(
                command=self.config.command,
                args=list(self.config.args),
                env=env,
                cwd=str(self.config.cwd or self.cwd),
                log_file=Path(os.devnull),
            )
        else:
            return SSETransport(url=self.config.url)

    async def connect(self) -> None:
        if self.status == MCPServerStatus.CONNECTED:
            return

        self.status = MCPServerStatus.CONNECTING

        try:
            self._client = Client(transport=self._create_transport())

            await self._client.__aenter__()

            tool_result = await self._client.list_tools()
            for tool in tool_result:
                self._tools[tool.name] = MCPToolInfo(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=(
                        tool.inputSchema if hasattr(tool, "inputSchema") else {}
                    ),
                    server_name=self.name,
                )

            self.status = MCPServerStatus.CONNECTED
        except Exception:
            self.status = MCPServerStatus.ERROR
            raise

    async def disconnect(self) -> None:
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None

        self._tools.clear()
        self.status = MCPServerStatus.DISCONNECTED

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]):
        if not self._client or self.status != MCPServerStatus.CONNECTED:
            raise RuntimeError(f"Not connected to server {self.name}")

        result = await self._client.call_tool(tool_name, arguments)

        output = []
        for item in result.content:
            if hasattr(item, "text"):
                output.append(item.text)
            else:
                output.append(str(item))

        return {
            "output": "\n".join(output),
            "is_error": result.is_error,
        }

    async def read_resource(self, uri: str) -> str:
        """Read an MCP resource by URI. Returns the text content."""
        if not self._client or self.status != MCPServerStatus.CONNECTED:
            raise RuntimeError(f"Not connected to server {self.name}")

        contents = await self._client.read_resource(uri)
        parts = []
        for item in contents:
            if hasattr(item, "text"):
                parts.append(item.text)
            elif hasattr(item, "blob"):
                parts.append(f"[binary data: {len(item.blob)} bytes]")
            else:
                parts.append(str(item))
        return "\n".join(parts)

    async def list_resources(self) -> list[dict[str, Any]]:
        """List all resources available on this server."""
        if not self._client or self.status != MCPServerStatus.CONNECTED:
            return []

        try:
            resources = await self._client.list_resources()
            return [
                {
                    "uri": str(r.uri),
                    "name": r.name or "",
                    "description": r.description or "",
                    "mime_type": r.mimeType or "",
                }
                for r in resources
            ]
        except Exception:
            logger.debug(f"Failed to list resources from {self.name}", exc_info=True)
            return []


class EmbeddedMCPClient(MCPClient):
    """MCP client for in-process FastMCP servers.

    Instead of connecting via stdio or SSE, this client connects directly
    to a FastMCP server instance running in the same process. This avoids
    subprocess overhead and is used for builtin MCP servers (memory, context).
    """

    def __init__(self, name: str, server: FastMCP) -> None:
        # We don't have an MCPServerConfig; use a minimal placeholder
        self.name = name
        self.config = None  # type: ignore[assignment]
        self.cwd = Path(".")
        self.status = MCPServerStatus.DISCONNECTED
        self._client: Client | None = None
        self._server = server
        self._tools: dict[str, MCPToolInfo] = dict()

    def _create_transport(self):
        # For embedded servers, we pass the FastMCP instance directly
        # to the Client constructor — no transport object needed
        raise NotImplementedError("EmbeddedMCPClient uses server directly")

    async def connect(self) -> None:
        if self.status == MCPServerStatus.CONNECTED:
            return

        self.status = MCPServerStatus.CONNECTING

        try:
            # FastMCP Client accepts a FastMCP server instance directly
            # for in-process communication (no stdio/SSE)
            self._client = Client(self._server)
            await self._client.__aenter__()

            tool_result = await self._client.list_tools()
            for tool in tool_result:
                self._tools[tool.name] = MCPToolInfo(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=(
                        tool.inputSchema if hasattr(tool, "inputSchema") else {}
                    ),
                    server_name=self.name,
                )

            self.status = MCPServerStatus.CONNECTED
            logger.info(
                f"Embedded MCP server '{self.name}' connected: "
                f"{len(self._tools)} tools"
            )
        except Exception:
            self.status = MCPServerStatus.ERROR
            raise
