"""
Configuration management for AutoDevOS CLI.

Handles:
- Config file storage (~/.config/autodevos/config.toml)
- API key management (via keyring for security)
- Provider settings
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_data_dir
import tomlkit
from tomlkit import TOMLDocument

APP_NAME = "autodevos"

# Provider configurations
PROVIDERS = {
    "ollama": {
        "name": "Ollama (Local)",
        "requires_key": False,
        "default_model": "llama3.2",
        "default_url": "http://localhost:11434/v1",
    },
    "openai": {
        "name": "OpenAI",
        "requires_key": True,
        "default_model": "gpt-4o",
        "default_url": "https://api.openai.com/v1",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "requires_key": True,
        "default_model": "claude-sonnet-4-20250514",
        "default_url": "https://api.anthropic.com",
    },
    "gemini": {
        "name": "Google Gemini",
        "requires_key": True,
        "default_model": "gemini-1.5-pro",
        "default_url": "https://generativelanguage.googleapis.com/v1beta",
    },
    "openrouter": {
        "name": "OpenRouter",
        "requires_key": True,
        "default_model": "anthropic/claude-sonnet-4-20250514",
        "default_url": "https://openrouter.ai/api/v1",
    },
}


def get_config_dir() -> Path:
    """Get the config directory path."""
    return Path(user_config_dir(APP_NAME))


def get_data_dir() -> Path:
    """Get the data directory path."""
    return Path(user_data_dir(APP_NAME))


def get_config_path() -> Path:
    """Get the main config file path."""
    return get_config_dir() / "config.toml"


def ensure_config_dir() -> Path:
    """Ensure config directory exists."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def ensure_data_dir() -> Path:
    """Ensure data directory exists."""
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def load_config() -> TOMLDocument:
    """Load config from file or return empty document."""
    config_path = get_config_path()
    if config_path.exists():
        with open(config_path, "r") as f:
            return tomlkit.load(f)
    return tomlkit.document()


def save_config(config: TOMLDocument) -> None:
    """Save config to file."""
    ensure_config_dir()
    config_path = get_config_path()
    with open(config_path, "w") as f:
        tomlkit.dump(config, f)


def get_api_key(provider: str) -> str | None:
    """Get API key for provider.
    
    Tries in order:
    1. Environment variable (API_KEY or <PROVIDER>_API_KEY)
    2. Keyring (secure storage)
    3. Config file (less secure, not recommended for keys)
    """
    # Check environment variables first
    env_key = os.environ.get("API_KEY")
    if env_key:
        return env_key
    
    provider_env_key = os.environ.get(f"{provider.upper()}_API_KEY")
    if provider_env_key:
        return provider_env_key
    
    # Try keyring for secure storage
    try:
        import keyring
        key = keyring.get_password(APP_NAME, f"{provider}_api_key")
        if key:
            return key
    except Exception:
        pass
    
    # Fallback to config file (not recommended for sensitive data)
    config = load_config()
    if "credentials" in config and provider in config["credentials"]:
        return config["credentials"][provider].get("api_key")
    
    return None


def set_api_key(provider: str, api_key: str, use_keyring: bool = True) -> None:
    """Store API key securely."""
    if use_keyring:
        try:
            import keyring
            keyring.set_password(APP_NAME, f"{provider}_api_key", api_key)
            return
        except Exception:
            pass
    
    # Fallback to config file
    config = load_config()
    if "credentials" not in config:
        config["credentials"] = tomlkit.table()
    if provider not in config["credentials"]:
        config["credentials"][provider] = tomlkit.table()
    config["credentials"][provider]["api_key"] = api_key
    save_config(config)


def delete_api_key(provider: str) -> None:
    """Remove API key from storage."""
    try:
        import keyring
        keyring.delete_password(APP_NAME, f"{provider}_api_key")
    except Exception:
        pass
    
    # Also remove from config file
    config = load_config()
    if "credentials" in config and provider in config["credentials"]:
        del config["credentials"][provider]
        save_config(config)


def get_provider() -> str:
    """Get current provider from config or default to ollama."""
    config = load_config()
    return config.get("model", {}).get("provider", "ollama")


def set_provider(provider: str) -> None:
    """Set the default provider."""
    config = load_config()
    if "model" not in config:
        config["model"] = tomlkit.table()
    config["model"]["provider"] = provider
    save_config(config)


def get_model() -> str | None:
    """Get current model from config."""
    config = load_config()
    return config.get("model", {}).get("name")


def set_model(model: str) -> None:
    """Set the default model."""
    config = load_config()
    if "model" not in config:
        config["model"] = tomlkit.table()
    config["model"]["name"] = model
    save_config(config)


def get_base_url() -> str | None:
    """Get custom base URL from config or environment."""
    url = os.environ.get("BASE_URL")
    if url:
        return url
    
    config = load_config()
    return config.get("model", {}).get("base_url")


def set_base_url(url: str) -> None:
    """Set custom base URL."""
    config = load_config()
    if "model" not in config:
        config["model"] = tomlkit.table()
    config["model"]["base_url"] = url
    save_config(config)


def is_configured() -> bool:
    """Check if the CLI has been configured."""
    config_path = get_config_path()
    if not config_path.exists():
        return False
    
    config = load_config()
    provider = config.get("model", {}).get("provider")
    if not provider:
        return False
    
    # For providers that require an API key, check if one exists
    provider_info = PROVIDERS.get(provider, {})
    if provider_info.get("requires_key", False):
        return get_api_key(provider) is not None
    
    return True


def get_full_config() -> dict[str, Any]:
    """Get full configuration as dict for the agent."""
    config = load_config()
    provider = config.get("model", {}).get("provider", "ollama")
    provider_info = PROVIDERS.get(provider, PROVIDERS["ollama"])
    
    return {
        "provider": provider,
        "model": config.get("model", {}).get("name") or provider_info["default_model"],
        "api_key": get_api_key(provider) or "",
        "base_url": get_base_url() or provider_info["default_url"],
        "temperature": config.get("model", {}).get("temperature", 1.0),
    }
