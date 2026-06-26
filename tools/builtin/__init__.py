from tools.builtin.apply_patch import ApplyPatchTool
from tools.builtin.edit_file import EditTool
from tools.builtin.glob import GlobTool
from tools.builtin.grep import GrepTool
from tools.builtin.list_dir import ListDirTool
from tools.builtin.read_file import ReadFileTool
from tools.builtin.shell import ShellTool
from tools.builtin.todo import TodosTool
from tools.builtin.web_fetch import WebFetchTool
from tools.builtin.web_search import WebSearchTool
from tools.builtin.write_file import WriteFileTool

# NOTE: MemoryTool has been replaced by the Memory MCP Server
# (tools/mcp/memory_server.py). Memory tools (mem_write, mem_read, etc.)
# are now registered via MCPManager as MCP tools.

__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "EditTool",
    "ApplyPatchTool",
    "ShellTool",
    "ListDirTool",
    "GrepTool",
    "GlobTool",
    "WebSearchTool",
    "WebFetchTool",
    "TodosTool",
]


def get_all_builtin_tools() -> list[type]:
    return [
        ReadFileTool,
        WriteFileTool,
        EditTool,
        ApplyPatchTool,
        ShellTool,
        ListDirTool,
        GrepTool,
        GlobTool,
        WebSearchTool,
        WebFetchTool,
        TodosTool,
    ]

