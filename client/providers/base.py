from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

from client.response import StreamEvent


class BaseProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Generate a chat completion response."""
        yield  # type: ignore

    @abstractmethod
    async def close(self) -> None:
        """Close any open connections."""
        pass

    def _build_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build tool definitions in OpenAI format. Override if provider uses different format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get(
                        "parameters",
                        {
                            "type": "object",
                            "properties": {},
                        },
                    ),
                },
            }
            for tool in tools
        ]
