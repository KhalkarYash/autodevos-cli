"""
Anthropic Claude provider.

Works with:
- Claude 3.5 Sonnet
- Claude 3 Opus
- Claude 3 Haiku
- All Anthropic models
"""

from __future__ import annotations
import asyncio
import uuid
from typing import Any, AsyncGenerator

import httpx

from autodevos.client.providers.base import BaseProvider
from autodevos.client.response import (
    StreamEvent,
    StreamEventType,
    TextDelta,
    TokenUsage,
    ToolCall,
    ToolCallDelta,
    parse_tool_call_arguments,
)


class AnthropicProvider(BaseProvider):
    """Provider for Anthropic's Claude API."""

    DEFAULT_BASE_URL = "https://api.anthropic.com"
    API_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        max_retries: int = 3,
    ) -> None:
        super().__init__(api_key, model, base_url or self.DEFAULT_BASE_URL)
        self._client: httpx.AsyncClient | None = None
        self._max_retries = max_retries

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self.API_VERSION,
                    "content-type": "application/json",
                },
                timeout=60.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _build_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert tools to Anthropic format."""
        return [
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get(
                    "parameters",
                    {
                        "type": "object",
                        "properties": {},
                    },
                ),
            }
            for tool in tools
        ]

    def _convert_messages(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert OpenAI-style messages to Anthropic format.
        
        Returns (system_prompt, messages)
        """
        system_prompt = None
        anthropic_messages = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                system_prompt = content
            elif role == "assistant":
                # Handle tool calls in assistant messages
                if "tool_calls" in msg:
                    content_blocks = []
                    if content:
                        content_blocks.append({"type": "text", "text": content})
                    for tc in msg["tool_calls"]:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "input": parse_tool_call_arguments(tc["function"]["arguments"]) 
                                if isinstance(tc["function"]["arguments"], str)
                                else tc["function"]["arguments"],
                        })
                    anthropic_messages.append({
                        "role": "assistant",
                        "content": content_blocks,
                    })
                else:
                    anthropic_messages.append({
                        "role": "assistant",
                        "content": content,
                    })
            elif role == "tool":
                # Anthropic expects tool results in user messages
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id"),
                    "content": content,
                }
                # Check if last message is user with tool_result, append to it
                if (
                    anthropic_messages
                    and anthropic_messages[-1]["role"] == "user"
                    and isinstance(anthropic_messages[-1]["content"], list)
                ):
                    anthropic_messages[-1]["content"].append(tool_result)
                else:
                    anthropic_messages.append({
                        "role": "user",
                        "content": [tool_result],
                    })
            elif role == "user":
                anthropic_messages.append({
                    "role": "user",
                    "content": content,
                })

        return system_prompt, anthropic_messages

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> AsyncGenerator[StreamEvent, None]:
        client = self._get_client()

        system_prompt, anthropic_messages = self._convert_messages(messages)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": 8192,
            "stream": stream,
        }

        if system_prompt:
            payload["system"] = system_prompt

        if tools:
            payload["tools"] = self._build_tools(tools)

        for attempt in range(self._max_retries + 1):
            try:
                if stream:
                    async for event in self._stream_response(client, payload):
                        yield event
                else:
                    async for event in self._non_stream_response(client, payload):
                        yield event
                return
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limit
                    if attempt < self._max_retries:
                        wait_time = 2**attempt
                        await asyncio.sleep(wait_time)
                    else:
                        yield StreamEvent(
                            type=StreamEventType.ERROR,
                            error=f"Rate limit exceeded: {e}",
                        )
                        return
                else:
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        error=f"API error: {e.response.text}",
                    )
                    return
            except httpx.ConnectError as e:
                if attempt < self._max_retries:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
                else:
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        error=f"Connection error: {e}",
                    )
                    return

    async def _stream_response(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
    ) -> AsyncGenerator[StreamEvent, None]:
        current_tool_use: dict[str, Any] | None = None
        tool_calls: list[dict[str, Any]] = []
        usage: TokenUsage | None = None

        async with client.stream("POST", "/v1/messages", json=payload) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                data = line[6:]  # Remove "data: " prefix
                if data == "[DONE]":
                    break

                try:
                    import json
                    event = json.loads(data)
                except:
                    continue

                event_type = event.get("type")

                if event_type == "message_start":
                    msg = event.get("message", {})
                    msg_usage = msg.get("usage", {})
                    usage = TokenUsage(
                        prompt_tokens=msg_usage.get("input_tokens", 0),
                        completion_tokens=0,
                        total_tokens=msg_usage.get("input_tokens", 0),
                    )

                elif event_type == "content_block_start":
                    block = event.get("content_block", {})
                    if block.get("type") == "tool_use":
                        current_tool_use = {
                            "id": block.get("id", str(uuid.uuid4())),
                            "name": block.get("name", ""),
                            "arguments": "",
                        }
                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_START,
                            tool_call_delta=ToolCallDelta(
                                call_id=current_tool_use["id"],
                                name=current_tool_use["name"],
                            ),
                        )

                elif event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    delta_type = delta.get("type")

                    if delta_type == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            yield StreamEvent(
                                type=StreamEventType.TEXT_DELTA,
                                text_delta=TextDelta(text),
                            )

                    elif delta_type == "input_json_delta" and current_tool_use:
                        partial_json = delta.get("partial_json", "")
                        current_tool_use["arguments"] += partial_json
                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_DELTA,
                            tool_call_delta=ToolCallDelta(
                                call_id=current_tool_use["id"],
                                name=current_tool_use["name"],
                                arguments_delta=partial_json,
                            ),
                        )

                elif event_type == "content_block_stop":
                    if current_tool_use:
                        tool_calls.append(current_tool_use)
                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_COMPLETE,
                            tool_call=ToolCall(
                                call_id=current_tool_use["id"],
                                name=current_tool_use["name"],
                                arguments=parse_tool_call_arguments(
                                    current_tool_use["arguments"]
                                ),
                            ),
                        )
                        current_tool_use = None

                elif event_type == "message_delta":
                    delta = event.get("delta", {})
                    msg_usage = event.get("usage", {})
                    if usage and msg_usage:
                        usage.completion_tokens = msg_usage.get("output_tokens", 0)
                        usage.total_tokens = (
                            usage.prompt_tokens + usage.completion_tokens
                        )

                elif event_type == "message_stop":
                    pass

        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            finish_reason="stop",
            usage=usage,
        )

    async def _non_stream_response(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
    ) -> AsyncGenerator[StreamEvent, None]:
        payload["stream"] = False
        response = await client.post("/v1/messages", json=payload)
        response.raise_for_status()

        data = response.json()

        text_content = ""
        tool_calls: list[ToolCall] = []

        for block in data.get("content", []):
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(
                        call_id=block.get("id", str(uuid.uuid4())),
                        name=block.get("name", ""),
                        arguments=block.get("input", {}),
                    )
                )

        usage_data = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("input_tokens", 0),
            completion_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("input_tokens", 0)
            + usage_data.get("output_tokens", 0),
        )

        # Emit tool calls first
        for tc in tool_calls:
            yield StreamEvent(
                type=StreamEventType.TOOL_CALL_COMPLETE,
                tool_call=tc,
            )

        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            text_delta=TextDelta(text_content) if text_content else None,
            finish_reason=data.get("stop_reason", "stop"),
            usage=usage,
        )
