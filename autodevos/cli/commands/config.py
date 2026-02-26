"""
Config command group for AutoDevOS CLI.

Usage:
    ados config                     # Show current config
    ados config show                # Show current config  
    ados config provider <name>     # Set provider (openai, anthropic, gemini, ollama)
    ados config model <name>        # Set model name
    ados config url <url>           # Set custom base URL
    ados config path                # Show config file path
    ados config edit                # Open config in editor
"""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from autodevos.cli.config_manager import (
    PROVIDERS,
    get_config_path,
    get_full_config,
    get_provider,
    set_provider,
    get_model,
    set_model,
    get_base_url,
    set_base_url,
    get_api_key,
    load_config,
)

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
def config(ctx):
    """Manage AutoDevOS configuration."""
    if ctx.invoked_subcommand is None:
        # Show current config
        show_config()


def show_config():
    """Display current configuration."""
    full_config = get_full_config()
    provider = full_config["provider"]
    provider_info = PROVIDERS.get(provider, {})
    
    table = Table(title="AutoDevOS Configuration", show_header=False, box=None)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")
    
    table.add_row("Provider", f"{provider} ({provider_info.get('name', 'Unknown')})")
    table.add_row("Model", full_config["model"])
    table.add_row("Base URL", full_config["base_url"])
    table.add_row("Temperature", str(full_config["temperature"]))
    
    # API Key status (masked)
    api_key = full_config["api_key"]
    if api_key and api_key != "ollama":
        key_display = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "****"
        table.add_row("API Key", f"✓ Set ({key_display})")
    elif provider_info.get("requires_key", False):
        table.add_row("API Key", "[red]✗ Not set[/red]")
    else:
        table.add_row("API Key", "[dim]Not required[/dim]")
    
    table.add_row("Config Path", str(get_config_path()))
    
    console.print()
    console.print(table)
    console.print()


@config.command("show")
def config_show():
    """Show current configuration."""
    show_config()


@config.command("provider")
@click.argument("name", required=False)
def config_provider(name: str | None):
    """Set or show the LLM provider."""
    if name is None:
        current = get_provider()
        console.print(f"Current provider: [cyan]{current}[/cyan]")
        console.print("\nAvailable providers:")
        for key, info in PROVIDERS.items():
            marker = "→" if key == current else " "
            requires = "[yellow](requires API key)[/yellow]" if info["requires_key"] else ""
            console.print(f"  {marker} [bold]{key}[/bold] - {info['name']} {requires}")
        return
    
    if name not in PROVIDERS:
        console.print(f"[red]Unknown provider: {name}[/red]")
        console.print(f"Available: {', '.join(PROVIDERS.keys())}")
        return
    
    set_provider(name)
    provider_info = PROVIDERS[name]
    console.print(f"[green]✓[/green] Provider set to [cyan]{name}[/cyan] ({provider_info['name']})")
    
    if provider_info["requires_key"] and not get_api_key(name):
        console.print(f"\n[yellow]⚠ {name} requires an API key.[/yellow]")
        console.print(f"  Run: [bold]ados auth set-key {name}[/bold]")


@config.command("model")
@click.argument("name", required=False)
def config_model(name: str | None):
    """Set or show the model name."""
    if name is None:
        current = get_model()
        provider = get_provider()
        default = PROVIDERS.get(provider, {}).get("default_model", "unknown")
        if current:
            console.print(f"Current model: [cyan]{current}[/cyan]")
        else:
            console.print(f"Using default: [cyan]{default}[/cyan]")
        return
    
    set_model(name)
    console.print(f"[green]✓[/green] Model set to [cyan]{name}[/cyan]")


@config.command("url")
@click.argument("url", required=False)
def config_url(url: str | None):
    """Set or show the custom base URL."""
    if url is None:
        current = get_base_url()
        provider = get_provider()
        default = PROVIDERS.get(provider, {}).get("default_url", "unknown")
        if current:
            console.print(f"Custom URL: [cyan]{current}[/cyan]")
        else:
            console.print(f"Using default: [cyan]{default}[/cyan]")
        return
    
    set_base_url(url)
    console.print(f"[green]✓[/green] Base URL set to [cyan]{url}[/cyan]")


@config.command("path")
def config_path():
    """Show config file path."""
    path = get_config_path()
    console.print(f"Config file: [cyan]{path}[/cyan]")
    if path.exists():
        console.print("[green]✓ File exists[/green]")
    else:
        console.print("[yellow]File not created yet[/yellow]")


@config.command("reset")
@click.confirmation_option(prompt="Are you sure you want to reset all configuration?")
def config_reset():
    """Reset configuration to defaults."""
    path = get_config_path()
    if path.exists():
        path.unlink()
    console.print("[green]✓[/green] Configuration reset to defaults")


@config.command("providers")
def config_providers():
    """List all available providers."""
    table = Table(title="Available Providers")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Default Model", style="green")
    table.add_column("API Key", style="yellow")
    
    current = get_provider()
    for key, info in PROVIDERS.items():
        name = info["name"]
        if key == current:
            name = f"→ {name}"
        requires = "Required" if info["requires_key"] else "Not needed"
        table.add_row(key, name, info["default_model"], requires)
    
    console.print()
    console.print(table)
    console.print()
