from urllib.parse import urlparse
import ipaddress
import socket

import httpx
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field


class WebFetchParams(BaseModel):
    url: str = Field(..., description="URL to fetch (must be http:// or https://)")
    timeout: int = Field(
        30,
        ge=5,
        le=120,
        description="Request timeout in seconds (default: 120)",
    )


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch content from a URL. Returns the response body as text"
    kind = ToolKind.NETWORK
    schema = WebFetchParams
    MAX_REDIRECTS = 5

    async def _validate_public_url(self, url: str) -> str | None:
        parsed = urlparse(url)
        if not parsed.scheme or parsed.scheme not in ("http", "https"):
            return "URL must be http:// or https://"

        if not parsed.hostname:
            return "URL must include a hostname"

        try:
            addresses = await asyncio_getaddrinfo(parsed.hostname, parsed.port)
        except OSError as e:
            return f"Could not resolve hostname: {e}"

        for address in addresses:
            ip = ipaddress.ip_address(address)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                return f"Refusing to fetch non-public address: {parsed.hostname}"

        return None

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebFetchParams(**invocation.params)

        validation_error = await self._validate_public_url(params.url)
        if validation_error:
            return ToolResult.error_result(validation_error)

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(params.timeout),
                follow_redirects=False,
            ) as client:
                url = params.url
                for _ in range(self.MAX_REDIRECTS + 1):
                    validation_error = await self._validate_public_url(url)
                    if validation_error:
                        return ToolResult.error_result(validation_error)

                    response = await client.get(url)

                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            return ToolResult.error_result(
                                "Redirect response missing Location header"
                            )
                        url = str(response.url.join(location))
                        continue

                    response.raise_for_status()
                    text = response.text
                    break
                else:
                    return ToolResult.error_result("Too many redirects")
        except httpx.HTTPStatusError as e:
            return ToolResult.error_result(
                f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
            )
        except Exception as e:
            return ToolResult.error_result(f"Request failed: {e}")

        if len(text) > 100 * 1024:
            text = text[: 100 * 1024] + "\n... [content truncated]"

        return ToolResult.success_result(
            text,
            metadata={
                "status_code": response.status_code,
                "content_length": len(response.content),
            },
        )


async def asyncio_getaddrinfo(hostname: str, port: int | None) -> list[str]:
    import asyncio

    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(
        hostname,
        port or 443,
        type=socket.SOCK_STREAM,
    )
    return [info[4][0] for info in infos]
