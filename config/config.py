from __future__ import annotations
from enum import Enum
import os
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field, model_validator


class Provider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"           # OpenAI API
    ANTHROPIC = "anthropic"     # Anthropic Claude
    GEMINI = "gemini"           # Google Gemini
    OLLAMA = "ollama"           # Local Ollama
    OPENROUTER = "openrouter"   # OpenRouter (multi-model)
    LMSTUDIO = "lmstudio"       # LM Studio local
    VLLM = "vllm"               # vLLM server
    CUSTOM = "custom"           # Custom OpenAI-compatible endpoint


# Default base URLs for each provider
PROVIDER_BASE_URLS = {
    Provider.OPENAI: "https://api.openai.com/v1",
    Provider.ANTHROPIC: "https://api.anthropic.com",
    Provider.GEMINI: "https://generativelanguage.googleapis.com/v1beta",
    Provider.OLLAMA: "http://localhost:11434/v1",
    Provider.OPENROUTER: "https://openrouter.ai/api/v1",
    Provider.LMSTUDIO: "http://localhost:1234/v1",
    Provider.VLLM: "http://localhost:8000/v1",
}

# Default models for each provider
PROVIDER_DEFAULT_MODELS = {
    Provider.OPENAI: "gpt-4o",
    Provider.ANTHROPIC: "claude-sonnet-4-20250514",
    Provider.GEMINI: "gemini-1.5-pro",
    Provider.OLLAMA: "llama3.2",
    Provider.OPENROUTER: "anthropic/claude-sonnet-4-20250514",
    Provider.LMSTUDIO: "local-model",
    Provider.VLLM: "local-model",
}


class ModelConfig(BaseModel):
    provider: Provider = Provider.OLLAMA
    name: str | None = None  # If None, uses provider default
    temperature: float = Field(default=1.0, ge=0.0, le=2.0)
    context_window: int = 128_000

    @property
    def model_name(self) -> str:
        """Get the model name, using provider default if not set."""
        if self.name:
            return self.name
        return PROVIDER_DEFAULT_MODELS.get(self.provider, "gpt-4o")


class ShellEnvironmentPolicy(BaseModel):
    ignore_default_excludes: bool = False
    exclude_patterns: list[str] = Field(
        default_factory=lambda: ["*KEY*", "*TOKEN*", "*SECRET*"]
    )
    set_vars: dict[str, str] = Field(default_factory=dict)


class MCPServerConfig(BaseModel):
    enabled: bool = True
    startup_timeout_sec: float = 10

    # stdio transport
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: Path | None = None

    # http/sse transport
    url: str | None = None

    @model_validator(mode="after")
    def validate_transport(self) -> MCPServerConfig:
        has_command = self.command is not None
        has_url = self.url is not None

        if not has_command and not has_url:
            raise ValueError(
                "MCP Server must have either 'command' (stdio) or 'url' (http/sse)"
            )

        if has_command and has_url:
            raise ValueError(
                "MCP Server cannot have both 'command' (stdio) and 'url' (http/sse)"
            )

        return self


class ApprovalPolicy(str, Enum):
    ON_REQUEST = "on-request"
    ON_FAILURE = "on-failure"
    AUTO = "auto"
    AUTO_EDIT = "auto-edut"
    NEVER = "never"
    YOLO = "yolo"


class HookTrigger(str, Enum):
    BEFORE_AGENT = "before_agent"
    AFTER_AGENT = "after_agent"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    ON_ERROR = "on_error"


class HookConfig(BaseModel):
    name: str
    trigger: HookTrigger
    command: str | None = None  # python3 tests.py
    script: str | None = None  # *.sh
    timeout_sec: float = 30
    enabled: bool = True

    @model_validator(mode="after")
    def validate_hook(self) -> HookConfig:
        if not self.command and not self.script:
            raise ValueError("Hook must either have 'command' or 'script'")
        return self


class Config(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    cwd: Path = Field(default_factory=Path.cwd)
    shell_environment: ShellEnvironmentPolicy = Field(
        default_factory=ShellEnvironmentPolicy
    )
    hooks_enabled: bool = False
    hooks: list[HookConfig] = Field(default_factory=list)
    approval: ApprovalPolicy = ApprovalPolicy.ON_REQUEST
    max_turns: int = 100
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)

    allowed_tools: list[str] | None = Field(
        None,
        description="If set, only these tools will be available to the agent",
    )

    developer_instructions: str | None = None
    user_instructions: str | None = None

    debug: bool = False

    @property
    def api_key(self) -> str:
        """Get API key from environment. Returns placeholder for Ollama."""
        key = os.environ.get("API_KEY", "")
        if not key and self.model.provider == Provider.OLLAMA:
            return "ollama"  # Ollama doesn't need a real key
        return key

    @property
    def base_url(self) -> str:
        """Get base URL from environment or use provider default."""
        url = os.environ.get("BASE_URL", "")
        if url:
            return url
        return PROVIDER_BASE_URLS.get(
            self.model.provider, 
            "http://localhost:11434/v1"
        )

    @property
    def provider(self) -> Provider:
        """Convenience property to access the provider."""
        return self.model.provider

    @property
    def model_name(self) -> str:
        return self.model.model_name

    @model_name.setter
    def model_name(self, value: str) -> None:
        self.model.name = value

    @property
    def temperature(self) -> float:
        return self.model.temperature

    @model_name.setter
    def temperature(self, value: str) -> None:
        self.model.temperature = value

    def validate(self) -> list[str]:
        errors: list[str] = []

        # Check if API key is required for the provider
        requires_key = self.model.provider in [
            Provider.OPENAI,
            Provider.ANTHROPIC,
            Provider.GEMINI,
            Provider.OPENROUTER,
        ]
        
        if requires_key and not self.api_key:
            errors.append(
                f"API_KEY required for {self.model.provider.value}. "
                "Set API_KEY environment variable"
            )

        if not self.cwd.exists():
            errors.append(f"Working directory does not exist: {self.cwd}")

        return errors

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
