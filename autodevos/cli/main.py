"""
Main CLI entry point for AutoDevOS.

This is the primary command that users will run:
    ados                    # Interactive session in current directory
    ados <directory>        # Open specific directory
    ados "prompt"           # Single prompt mode
    ados --init             # Initialize new project
"""

import asyncio
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from autodevos import __version__
from autodevos.cli.config_manager import (
    is_configured,
    get_full_config,
    get_config_dir,
    ensure_config_dir,
    ensure_data_dir,
    PROVIDERS,
)
from autodevos.cli.commands.config import config
from autodevos.cli.commands.auth import auth

console = Console()


def show_welcome():
    """Show welcome message for first-time users."""
    console.print(Panel.fit(
        "[bold cyan]Welcome to AutoDevOS![/bold cyan]\n\n"
        "AI-powered coding assistant for your terminal.\n\n"
        "To get started, run:\n"
        "  [bold]ados auth setup[/bold]",
        border_style="cyan",
    ))


def check_setup():
    """Check if CLI is set up and guide user if not."""
    if not is_configured():
        show_welcome()
        console.print("\n[yellow]Setup required before first use.[/yellow]")
        console.print("Run: [bold]ados auth setup[/bold]\n")
        return False
    return True


@click.group(invoke_without_command=True)
@click.argument("target", required=False)
@click.option(
    "--version", "-v",
    is_flag=True,
    help="Show version",
)
@click.option(
    "--init",
    is_flag=True,
    help="Initialize a new project in current directory",
)
@click.pass_context
def main(ctx, target: str | None, version: bool, init: bool):
    """
    AutoDevOS - AI-powered coding assistant for your terminal.
    
    \b
    Usage:
        ados                    Start interactive session
        ados <directory>        Open specific directory
        ados "prompt"           Run single prompt
        ados config             Manage configuration
        ados auth               Authentication & setup
    
    \b
    Examples:
        ados                    # Interactive mode in current directory
        ados ~/projects/myapp   # Open a specific project
        ados "create a todo app"  # Single command
        ados config provider anthropic  # Switch to Claude
    """
    if version:
        console.print(f"AutoDevOS CLI v{__version__}")
        return
    
    if ctx.invoked_subcommand is not None:
        return
    
    # Ensure directories exist
    ensure_config_dir()
    ensure_data_dir()
    
    if init:
        # Initialize new project
        init_project()
        return
    
    # Check setup
    if not check_setup():
        return
    
    # Determine working directory
    if target:
        target_path = Path(target).expanduser().resolve()
        
        # Check if target looks like a prompt (contains spaces, not a path)
        if " " in target and not target_path.exists():
            # It's a prompt, run in single mode
            asyncio.run(run_agent(Path.cwd(), prompt=target))
            return
        
        if not target_path.exists():
            console.print(f"[red]Directory not found: {target}[/red]")
            sys.exit(1)
        
        if not target_path.is_dir():
            console.print(f"[red]Not a directory: {target}[/red]")
            sys.exit(1)
        
        cwd = target_path
    else:
        cwd = Path.cwd()
    
    # Run the agent
    asyncio.run(run_agent(cwd))


def init_project():
    """Initialize a new project in current directory."""
    cwd = Path.cwd()
    agent_dir = cwd / ".autodevos"
    config_file = agent_dir / "config.toml"
    
    if config_file.exists():
        console.print("[yellow]Project already initialized[/yellow]")
        console.print(f"  Config: {config_file}")
        return
    
    agent_dir.mkdir(exist_ok=True)
    
    # Create default project config
    default_config = """# AutoDevOS Project Configuration
# This file customizes the agent for this specific project

# Project-specific instructions for the AI
# developer_instructions = \"\"\"
# This is a Python web application using FastAPI.
# Follow PEP 8 style guidelines.
# \"\"\"

# Tool restrictions (optional)
# allowed_tools = ["read_file", "write_file", "shell"]

# Approval policy: on-request, auto, never, yolo
# approval = "on-request"
"""
    
    config_file.write_text(default_config)
    console.print(f"[green]✓[/green] Initialized AutoDevOS project")
    console.print(f"  Config: {config_file}")
    console.print("\nEdit the config file to customize the agent for your project.")


async def run_agent(cwd: Path, prompt: str | None = None):
    """Run the agent in the specified directory."""
    # Import here to avoid circular imports and speed up CLI startup
    # These imports pull in the heavy dependencies
    
    # Add the package root to path for imports to work
    package_root = Path(__file__).parent.parent.parent
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    
    # Set up environment from our config
    cli_config = get_full_config()
    
    # Export to environment for the agent to pick up
    os.environ["API_KEY"] = cli_config["api_key"]
    os.environ["BASE_URL"] = cli_config["base_url"]
    
    # Now import the agent components
    from agent.agent import Agent
    from agent.events import AgentEventType
    from config.config import Config, Provider, ModelConfig
    from config.loader import load_config
    from ui.tui import TUI, get_console
    
    # Load project config
    project_config = load_config(cwd)
    
    # Override with CLI config
    project_config.model.provider = Provider(cli_config["provider"])
    project_config.model.name = cli_config["model"]
    project_config.cwd = cwd
    
    # Validate
    errors = project_config.validate()
    if errors:
        for error in errors:
            console.print(f"[red]{error}[/red]")
        sys.exit(1)
    
    # Create TUI
    tui_console = get_console()
    tui = TUI(project_config, tui_console)
    
    # Create CLI handler
    cli_handler = CLIHandler(project_config, tui, tui_console)
    
    if prompt:
        # Single prompt mode
        await cli_handler.run_single(prompt)
    else:
        # Interactive mode
        await cli_handler.run_interactive()


class CLIHandler:
    """Handles CLI interactions with the agent."""
    
    def __init__(self, config, tui, console):
        self.config = config
        self.tui = tui
        self.console = console
        self.agent = None
    
    async def run_single(self, message: str) -> str | None:
        from agent.agent import Agent
        
        async with Agent(self.config) as agent:
            self.agent = agent
            return await self._process_message(message)
    
    async def run_interactive(self) -> None:
        from agent.agent import Agent
        from agent.events import AgentEventType
        from config.config import ApprovalPolicy
        
        provider_name = PROVIDERS.get(self.config.provider.value, {}).get("name", self.config.provider.value)
        
        self.tui.print_welcome(
            "AutoDevOS",
            lines=[
                f"provider: {provider_name}",
                f"model: {self.config.model_name}",
                f"cwd: {self.config.cwd}",
                "commands: /help /config /tools /save /exit",
            ],
        )
        
        async with Agent(
            self.config,
            confirmation_callback=self.tui.handle_confirmation,
        ) as agent:
            self.agent = agent
            
            while True:
                try:
                    user_input = self.console.input("\n[user]>[/user] ").strip()
                    if not user_input:
                        continue
                    
                    if user_input.startswith("/"):
                        should_continue = await self._handle_command(user_input)
                        if not should_continue:
                            break
                        continue
                    
                    await self._process_message(user_input)
                except KeyboardInterrupt:
                    self.console.print("\n[dim]Use /exit to quit[/dim]")
                except EOFError:
                    break
        
        self.console.print("\n[dim]Goodbye![/dim]")
    
    def _get_tool_kind(self, tool_name: str) -> str | None:
        tool = self.agent.session.tool_registry.get(tool_name)
        if not tool:
            return None
        return tool.kind.value
    
    async def _process_message(self, message: str) -> str | None:
        from agent.events import AgentEventType
        
        if not self.agent:
            return None
        
        assistant_streaming = False
        final_response: str | None = None
        
        async for event in self.agent.run(message):
            if event.type == AgentEventType.TEXT_DELTA:
                content = event.data.get("content", "")
                if not assistant_streaming:
                    self.tui.begin_assistant()
                    assistant_streaming = True
                self.tui.stream_assistant_delta(content)
            elif event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content")
                if assistant_streaming:
                    self.tui.end_assistant()
                    assistant_streaming = False
            elif event.type == AgentEventType.AGENT_ERROR:
                error = event.data.get("error", "Unknown error")
                self.console.print(f"\n[error]Error: {error}[/error]")
            elif event.type == AgentEventType.TOOL_CALL_START:
                tool_name = event.data.get("name", "unknown")
                tool_kind = self._get_tool_kind(tool_name)
                self.tui.tool_call_start(
                    event.data.get("call_id", ""),
                    tool_name,
                    tool_kind,
                    event.data.get("arguments", {}),
                )
            elif event.type == AgentEventType.TOOL_CALL_COMPLETE:
                tool_name = event.data.get("name", "unknown")
                tool_kind = self._get_tool_kind(tool_name)
                self.tui.tool_call_complete(
                    event.data.get("call_id", ""),
                    tool_name,
                    tool_kind,
                    event.data.get("success", False),
                    event.data.get("output", ""),
                    event.data.get("error"),
                    event.data.get("metadata"),
                    event.data.get("diff"),
                    event.data.get("truncated", False),
                    event.data.get("exit_code"),
                )
        
        return final_response
    
    async def _handle_command(self, command: str) -> bool:
        """Handle slash commands. Returns True to continue, False to exit."""
        from agent.persistence import PersistenceManager, SessionSnapshot
        from config.config import ApprovalPolicy
        
        cmd = command.lower().strip()
        parts = cmd.split(maxsplit=1)
        cmd_name = parts[0]
        cmd_args = parts[1] if len(parts) > 1 else ""
        
        if cmd_name in ("/exit", "/quit"):
            return False
        elif cmd_name == "/help":
            self.tui.show_help()
        elif cmd_name == "/clear":
            self.agent.session.context_manager.clear()
            self.agent.session.loop_detector.clear()
            self.console.print("[success]Conversation cleared[/success]")
        elif cmd_name == "/config":
            self.console.print("\n[bold]Current Configuration[/bold]")
            self.console.print(f"  Provider: {self.config.provider.value}")
            self.console.print(f"  Model: {self.config.model_name}")
            self.console.print(f"  Temperature: {self.config.temperature}")
            self.console.print(f"  Approval: {self.config.approval.value}")
            self.console.print(f"  Working Dir: {self.config.cwd}")
        elif cmd_name == "/tools":
            tools = self.agent.session.tool_registry.get_tools()
            self.console.print(f"\n[bold]Available Tools ({len(tools)})[/bold]")
            for tool in tools:
                self.console.print(f"  • {tool.name}")
        elif cmd_name == "/stats":
            stats = self.agent.session.get_stats()
            self.console.print("\n[bold]Session Statistics[/bold]")
            for key, value in stats.items():
                self.console.print(f"  {key}: {value}")
        elif cmd_name == "/save":
            persistence_manager = PersistenceManager()
            session_snapshot = SessionSnapshot(
                session_id=self.agent.session.session_id,
                created_at=self.agent.session.created_at,
                updated_at=self.agent.session.updated_at,
                turn_count=self.agent.session.turn_count,
                messages=self.agent.session.context_manager.get_messages(),
                total_usage=self.agent.session.context_manager.total_usage,
            )
            persistence_manager.save_session(session_snapshot)
            self.console.print(f"[success]Session saved: {self.agent.session.session_id}[/success]")
        else:
            self.console.print(f"[error]Unknown command: {cmd_name}[/error]")
        
        return True


# Add subcommands
main.add_command(config)
main.add_command(auth)


@main.command()
def version():
    """Show version information."""
    console.print(f"AutoDevOS CLI v{__version__}")


if __name__ == "__main__":
    main()
