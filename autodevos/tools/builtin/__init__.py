from autodevos.tools.builtin.edit_file import EditTool
from autodevos.tools.builtin.glob import GlobTool
from autodevos.tools.builtin.grep import GrepTool
from autodevos.tools.builtin.list_dir import ListDirTool
from autodevos.tools.builtin.memory import MemoryTool
from autodevos.tools.builtin.read_file import ReadFileTool
from autodevos.tools.builtin.shell import ShellTool
from autodevos.tools.builtin.todo import TodosTool
from autodevos.tools.builtin.web_fetch import WebFetchTool
from autodevos.tools.builtin.web_search import WebSearchTool
from autodevos.tools.builtin.write_file import WriteFileTool

__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "EditTool",
    "ShellTool",
    "ListDirTool",
    "GrepTool",
    "GlobTool",
    "WebSearchTool",
    "WebFetchTool",
    "TodosTool",
    "MemoryTool",
]


def get_all_builtin_tools() -> list[type]:
    return [
        ReadFileTool,
        WriteFileTool,
        EditTool,
        ShellTool,
        ListDirTool,
        GrepTool,
        GlobTool,
        WebSearchTool,
        WebFetchTool,
        TodosTool,
        MemoryTool,
    ]
