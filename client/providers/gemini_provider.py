"""
Google Gemini provider.

Works with:
- Gemini 1.5 Pro
- Gemini 1.5 Flash
- Gemini 1.0 Pro
- All Google Gemini models
"""

from __future__ import annotations
import asyncio
import uuid
from typing import Any, AsyncGenerator

import httpx

from client.providers.base import BaseProvider
from client.response import (
    StreamEvent,
    StreamEventType,
    TextDelta,
    TokenUsage,
    ToolCall,
    ToolCallDelta,
    parse_tool_call_arguments,
)


class GeminiProvider(BaseProvider):
    """Provider for Google's Gemini API."""

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

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
                headers={"content-type": "application/json"},
                timeout=60.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _build_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert tools to Gemini format."""
        function_declarations = []
        for tool in tools:
            params = tool.get("parameters", {"type": "object", "properties": {}})
            # Gemini doesn't like "additionalProperties" in some cases
            params_clean = {
                "type": params.get("type", "object"),
                "properties": params.get("properties", {}),
            }
            if "required" in params:
                params_clean["required"] = params["required"]

            function_declarations.append({
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": params_clean,
            })

        return [{"functionDeclarations": function_declarations}]

    def _convert_messages(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert OpenAI-style messages to Gemini format.
        
        Returns (system_instruction, contents)
        """
        system_instruction = None
        contents = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                system_instruction = content
            elif role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": content}],
                })
            elif role == "assistant":
                parts = []
                if content:
                    parts.append({"text": content})

                # Handle tool calls
                if "tool_calls" in msg:
                    for tc in msg["tool_calls"]:
                        args = tc["function"]["arguments"]
                        if isinstance(args, str):
                            args = parse_tool_call_arguments(args)
                        parts.append({
                            "functionCall": {
                                "name": tc["function"]["name"],
                                "args": args,
                            }
                        })

                contents.append({
                    "role": "model",
                    "parts": parts,
                })
            elif role == "tool":
                # Gemini expects function responses in user turn
                tool_response = {
                    "functionResponse": {
                        "name": msg.get("name", "unknown"),
                        "response": {"result": content},
                    }
                }
                # Append to last user message or create new one
                if contents and contents[-1]["role"] == "user":
                    contents[-1]["parts"].append(tool_response)
                else:
                    contents.append({
                        "role": "user",
                        "parts": [tool_response],
                    })

        return system_instruction, contents

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> AsyncGenerator[StreamEvent, None]:
        client = self._get_client()

        system_instruction, contents = self._convert_messages(messages)

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": 1.0,
                "maxOutputTokens": 8192,
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        if tools:
            payload["tools"] = self._build_tools(tools)

        endpoint = f"/models/{self.model}:{'streamGenerateContent' if stream else 'generateContent'}"
        url = f"{endpoint}?key={self.api_key}"

        if stream:
            url += "&alt=sse"

        for attempt in range(self._max_retries + 1):
            try:
                if stream:
                    async for event in self._stream_response(client, url, payload):
                        yield event
                else:
                    async for event in self._non_stream_response(client, url, payload):
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
        url: str,
        payload: dict[str, Any],
    ) -> AsyncGenerator[StreamEvent, None]:
        import json

        tool_calls: list[dict[str, Any]] = []
        usage: TokenUsage | None = None

        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if not data_str:
                    continue

                try:
                    data = json.loads(data_str)
                except:
                    continue

                # Extract usage metadata
                usage_meta = data.get("usageMetadata", {})
                if usage_meta:
                    usage = TokenUsage(
                        prompt_tokens=usage_meta.get("promptTokenCount", 0),
                        completion_tokens=usage_meta.get("candidatesTokenCount", 0),
                        total_tokens=usage_meta.get("totalTokenCount", 0),
                    )

                candidates = data.get("candidates", [])
                if not candidates:
                    continue

                candidate = candidates[0]
                content = candidate.get("content", {})
                parts = content.get("parts", [])

                for part in parts:
                    if "text" in part:
                        yield StreamEvent(
                            type=StreamEventType.TEXT_DELTA,
                            text_delta=TextDelta(part["text"]),
                        )

                    if "functionCall" in part:
                        fc = part["functionCall"]
                        call_id = str(uuid.uuid4())
                        tool_call = {
                            "id": call_id,
                            "name": fc.get("name", ""),
                            "arguments": fc.get("args", {}),
                        }
                        tool_calls.append(tool_call)

                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_START,
                            tool_call_delta=ToolCallDelta(
                                call_id=call_id,
                                name=tool_call["name"],
                            ),
                        )

                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_COMPLETE,
                            tool_call=ToolCall(
                                call_id=call_id,
                                name=tool_call["name"],
                                arguments=tool_call["arguments"],
                            ),
                        )

        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            finish_reason="stop",
            usage=usage,
        )

    async def _non_stream_response(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: dict[str, Any],
    ) -> AsyncGenerator[StreamEvent, None]:
        response = await client.post(url, json=payload)
        response.raise_for_status()

        data = response.json()

        text_content = ""
        tool_calls: list[ToolCall] = []

        candidates = data.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            for part in content.get("parts", []):
                if "text" in part:
                    text_content += part["text"]
                if "functionCall" in part:
                    fc = part["functionCall"]
                    tool_calls.append(
                        ToolCall(
                            call_id=str(uuid.uuid4()),
                            name=fc.get("name", ""),
                            arguments=fc.get("args", {}),
                        )
                    )

        usage_meta = data.get("usageMetadata", {})
        usage = TokenUsage(
            prompt_tokens=usage_meta.get("promptTokenCount", 0),
            completion_tokens=usage_meta.get("candidatesTokenCount", 0),
            total_tokens=usage_meta.get("totalTokenCount", 0),
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
            finish_reason="stop",
            usage=usage,
        )
