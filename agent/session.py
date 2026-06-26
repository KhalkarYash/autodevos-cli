import logging
from datetime import datetime
from typing import Any
import uuid
from client.llm_client import LLMClient
from config.config import Config
from context.compaction import ChatCompactor
from context.loop_detector import LoopDetector
from context.manager import ContextManager
from hooks.hook_system import HookSystem
from safety.approval import ApprovalManager
from agent.persistence import PersistenceManager, SessionSnapshot
from tools.discovery import ToolDiscoveryManager
from tools.mcp.mcp_manager import MCPManager
from tools.registry import create_default_registry

logger = logging.getLogger(__name__)


class Session:
    def __init__(self, config: Config):
        self.config = config
        self.client = LLMClient(config=config)
        self.tool_registry = create_default_registry(config)
        self.context_manager: ContextManager | None = None
        self.discovery_manager = ToolDiscoveryManager(
            self.config,
            self.tool_registry,
        )
        self.mcp_manager = MCPManager(self.config)
        self.chat_compactor = ChatCompactor(self.client)
        self.approval_manager = ApprovalManager(
            self.config.approval,
            self.config.cwd,
        )
        self.loop_detector = LoopDetector()
        self.hook_system = HookSystem(config)
        self.session_id = str(uuid.uuid4())
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

        self.turn_count = 0

    async def initialize(self) -> None:
        if self.context_manager is not None:
            return

        await self.mcp_manager.initialize()
        self.mcp_manager.register_tools(self.tool_registry)

        self.discovery_manager.discover_all()
        self.context_manager = ContextManager(
            config=self.config,
            user_memory=self._load_memory(),
            tools=self.tool_registry.get_tools(),
        )

        # Bind the Context MCP Server to the live ContextManager
        context_store = self.mcp_manager.get_context_store()
        if context_store:
            context_store.bind_context_manager(self.context_manager)
            logger.debug("Context MCP server bound to ContextManager")

    def _load_memory(self) -> str | None:
        """Load user memory from the Memory MCP Server store.

        Reads directly from the MemoryStore (which backs the MCP server)
        rather than reading the legacy JSON file. The MemoryStore handles
        migration from user_memory.json on first access.
        """
        memory_store = self.mcp_manager.get_memory_store()
        if memory_store is None:
            logger.debug("Memory MCP server not available; no user memory loaded")
            return None

        try:
            user_mem = memory_store.get_all_formatted("user")
            project_mem = memory_store.get_all_formatted("project")

            parts = []
            if user_mem and "No user memories" not in user_mem:
                parts.append(user_mem)
            if project_mem and "No project memories" not in project_mem:
                parts.append(project_mem)

            return "\n\n".join(parts) if parts else None
        except Exception:
            logger.debug("Failed to load memory from MCP server", exc_info=True)
            return None

    def increment_turn(self) -> int:
        self.turn_count += 1
        self.updated_at = datetime.now()

        return self.turn_count

    def get_stats(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "turn_count": self.turn_count,
            "message_count": self.context_manager.message_count
            if self.context_manager
            else 0,
            "token_usage": self.context_manager.total_usage
            if self.context_manager
            else None,
            "tools_count": len(self.tool_registry.get_tools()),
            "mcp_servers": len(self.tool_registry.connected_mcp_servers),
        }

    def snapshot(self) -> SessionSnapshot:
        if self.context_manager is None:
            raise RuntimeError("Session is not initialized")

        return SessionSnapshot(
            session_id=self.session_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
            turn_count=self.turn_count,
            messages=self.context_manager.get_messages(),
            total_usage=self.context_manager.total_usage,
        )

    def load_snapshot(self, snapshot: SessionSnapshot) -> None:
        if self.context_manager is None:
            raise RuntimeError("Session is not initialized")

        self.session_id = snapshot.session_id
        self.created_at = snapshot.created_at
        self.updated_at = snapshot.updated_at
        self.turn_count = snapshot.turn_count
        self.context_manager.total_usage = snapshot.total_usage
        self.context_manager.load_messages(snapshot.messages)

    def save_session(self) -> None:
        PersistenceManager().save_session(self.snapshot())

    def create_checkpoint(self, name: str | None = None) -> str:
        return PersistenceManager().save_checkpoint(self.snapshot())

    def list_checkpoints(self) -> list[dict[str, Any]]:
        return PersistenceManager().list_checkpoints()

    def restore_checkpoint(self, checkpoint_id: str) -> bool:
        snapshot = PersistenceManager().load_checkpoint(checkpoint_id)
        if not snapshot:
            return False
        self.load_snapshot(snapshot)
        return True
