"""
LLM Client - Multi-provider support for LLM interactions.

Supports:
- OpenAI (gpt-4o, gpt-4, etc.)
- Anthropic (Claude 3.5 Sonnet, Claude 3 Opus, etc.)
- Google Gemini (gemini-1.5-pro, gemini-1.5-flash, etc.)
- Ollama (llama3.2, mistral, codellama, etc.)
- OpenRouter (any model via openrouter.ai)
- LM Studio, vLLM, and other OpenAI-compatible servers
"""

from typing import Any, AsyncGenerator

from autodevos.client.response import StreamEvent
from autodevos.client.providers.base import BaseProvider
from autodevos.client.providers.openai_provider import OpenAIProvider
from autodevos.client.providers.anthropic_provider import AnthropicProvider
from autodevos.client.providers.gemini_provider import GeminiProvider
from autodevos.config.config import Config, Provider


class LLMClient:
    """Multi-provider LLM client."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._provider: BaseProvider | None = None

    def _create_provider(self) -> BaseProvider:
        """Create the appropriate provider based on config."""
        provider_type = self.config.provider
        api_key = self.config.api_key
        model = self.config.model_name
        base_url = self.config.base_url

        if provider_type == Provider.ANTHROPIC:
            return AnthropicProvider(
                api_key=api_key,
                model=model,
                base_url=base_url if base_url != "https://api.anthropic.com" else None,
            )
        elif provider_type == Provider.GEMINI:
            return GeminiProvider(
                api_key=api_key,
                model=model,
                base_url=base_url if "googleapis.com" not in base_url else None,
            )
        else:
            # OpenAI-compatible providers: openai, ollama, openrouter, lmstudio, vllm, custom
            return OpenAIProvider(
                api_key=api_key,
                model=model,
                base_url=base_url,
            )

    def get_provider(self) -> BaseProvider:
        """Get or create the provider instance."""
        if self._provider is None:
            self._provider = self._create_provider()
        return self._provider

    async def close(self) -> None:
        """Close the provider connection."""
        if self._provider:
            await self._provider.close()
            self._provider = None

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Generate a chat completion using the configured provider."""
        provider = self.get_provider()
        async for event in provider.chat_completion(messages, tools, stream):
            yield event
