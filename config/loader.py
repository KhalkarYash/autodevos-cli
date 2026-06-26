import os
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_data_dir
import tomli

from config.config import Config
from utils.errors import ConfigError
import logging

logger = logging.getLogger(__name__)
CONFIG_FILE_NAME = "config.toml"

AGENT_MD_FILE = "AGENTS.md"


def get_config_dir() -> Path:
    """Config directory. Override with AUTODEVOS_CONFIG_DIR for containers/tests."""
    override = os.environ.get("AUTODEVOS_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path(user_config_dir("ai-agent"))


def get_data_dir() -> Path:
    """Data directory. Override with AUTODEVOS_DATA_DIR for containers/tests."""
    override = os.environ.get("AUTODEVOS_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path(user_data_dir("ai-agent"))


def get_system_config_path() -> Path:
    return get_config_dir() / CONFIG_FILE_NAME


def _parse_toml(path: Path):
    try:
        with open(path, "rb") as f:
            return tomli.load(f)
    except tomli.TOMLDecodeError as e:
        raise ConfigError(f"Invalid TOML in {path}: {e}", config_file=str(path)) from e
    except (OSError, IOError) as e:
        raise ConfigError(
            f"Failed to read config file {path}: {e}", config_file=str(path)
        ) from e


def _get_project_config(cwd: Path) -> Path | None:
    current = cwd.resolve()
    agent_dir = current / ".ai-agent"

    if agent_dir.is_dir():
        config_file = agent_dir / CONFIG_FILE_NAME
        if config_file.is_file():
            return config_file

    return None


def _get_agent_md_files(cwd: Path) -> str | None:
    current = cwd.resolve()
    files: list[Path] = []

    for directory in [current, *current.parents]:
        agent_md_file = directory / AGENT_MD_FILE
        if agent_md_file.is_file():
            files.append(agent_md_file)

    if not files:
        return None

    sections = []
    for file_path in reversed(files):
        content = file_path.read_text(encoding="utf-8")
        sections.append(f"# {file_path}\n\n{content}")

    return "\n\n".join(sections)


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def load_config(cwd: Path | None) -> Config:
    cwd = cwd or Path.cwd()

    system_path = get_system_config_path()

    config_dict: dict[str, Any] = {}

    if system_path.is_file():
        try:
            config_dict = _parse_toml(system_path)
        except ConfigError:
            logger.warning(f"Skipping invalid system config: {system_path}")

    project_path = _get_project_config(cwd)
    if project_path:
        try:
            project_config_dict = _parse_toml(project_path)
            config_dict = _merge_dicts(config_dict, project_config_dict)
        except ConfigError:
            logger.warning(f"Skipping invalid system config: {system_path}")

    if "cwd" not in config_dict:
        config_dict["cwd"] = cwd

    if "developer_instructions" not in config_dict:
        agent_md_content = _get_agent_md_files(cwd)
        if agent_md_content:
            config_dict["developer_instructions"] = agent_md_content

    try:
        config = Config(**config_dict)
    except Exception as e:
        raise ConfigError(f"Invalid configuration: {e}") from e

    return config
