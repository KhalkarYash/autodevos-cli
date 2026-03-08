"""
Auth command group for AutoDevOS CLI.

Usage:
    ados auth                       # Show auth status
    ados auth set-key <provider>    # Set API key for provider
    ados auth remove-key <provider> # Remove API key
    ados auth setup                 # Interactive setup wizard
    ados auth setup-token <token>   # Setup from dashboard token (base64 encoded config)
"""

import base64
import json
import click
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

from autodevos.cli.config_manager import (
    PROVIDERS,
    get_api_key,
    set_api_key,
    delete_api_key,
    get_provider,
    set_provider,
    set_model,
    set_base_url,
    is_configured,
)

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
def auth(ctx):
    """Manage authentication and API keys."""
    if ctx.invoked_subcommand is None:
        show_auth_status()


def show_auth_status():
    """Show authentication status for all providers."""
    console.print("\n[bold]Authentication Status[/bold]\n")
    
    current_provider = get_provider()
    
    for provider, info in PROVIDERS.items():
        marker = "→" if provider == current_provider else " "
        if info["requires_key"]:
            key = get_api_key(provider)
            if key:
                key_preview = f"{key[:8]}..." if len(key) > 8 else "****"
                status = f"[green]✓ Set[/green] ({key_preview})"
            else:
                status = "[red]✗ Not set[/red]"
        else:
            status = "[dim]Not required[/dim]"
        
        console.print(f"  {marker} [cyan]{provider:12}[/cyan] {status}")
    
    console.print()
    
    if not is_configured():
        console.print("[yellow]⚠ Setup incomplete. Run:[/yellow] [bold]ados auth setup[/bold]")
    else:
        console.print("[green]✓ Ready to use![/green]")


@auth.command("set-key")
@click.argument("provider")
@click.argument("key", required=False)
def auth_set_key(provider: str, key: str | None):
    """Set API key for a provider."""
    if provider not in PROVIDERS:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        console.print(f"Available: {', '.join(PROVIDERS.keys())}")
        return
    
    if not PROVIDERS[provider]["requires_key"]:
        console.print(f"[yellow]{provider} doesn't require an API key[/yellow]")
        return
    
    if key is None:
        # Prompt for key (hidden input)
        key = Prompt.ask(
            f"Enter API key for {provider}",
            password=True,
        )
    
    if not key:
        console.print("[red]API key cannot be empty[/red]")
        return
    
    set_api_key(provider, key)
    console.print(f"[green]✓[/green] API key set for [cyan]{provider}[/cyan]")


@auth.command("remove-key")
@click.argument("provider")
def auth_remove_key(provider: str):
    """Remove API key for a provider."""
    if provider not in PROVIDERS:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        return
    
    delete_api_key(provider)
    console.print(f"[green]✓[/green] API key removed for [cyan]{provider}[/cyan]")


@auth.command("setup")
def auth_setup():
    """Interactive setup wizard."""
    console.print(Panel.fit(
        "[bold cyan]AutoDevOS Setup Wizard[/bold cyan]\n\n"
        "Let's configure your AI coding assistant!",
        border_style="cyan",
    ))
    console.print()
    
    # Step 1: Choose provider
    console.print("[bold]Step 1: Choose your LLM provider[/bold]\n")
    
    for i, (key, info) in enumerate(PROVIDERS.items(), 1):
        requires = " [yellow](requires API key)[/yellow]" if info["requires_key"] else " [green](no API key needed)[/green]"
        console.print(f"  {i}. [cyan]{info['name']}[/cyan]{requires}")
    
    console.print()
    
    choice = Prompt.ask(
        "Select provider (1-5)",
        choices=["1", "2", "3", "4", "5"],
        default="1",
    )
    
    provider_keys = list(PROVIDERS.keys())
    selected_provider = provider_keys[int(choice) - 1]
    provider_info = PROVIDERS[selected_provider]
    
    set_provider(selected_provider)
    console.print(f"\n[green]✓[/green] Selected: {provider_info['name']}\n")
    
    # Step 2: API Key (if needed)
    if provider_info["requires_key"]:
        console.print("[bold]Step 2: Enter your API key[/bold]\n")
        
        if selected_provider == "openai":
            console.print("  Get your key at: https://platform.openai.com/api-keys")
        elif selected_provider == "anthropic":
            console.print("  Get your key at: https://console.anthropic.com/settings/keys")
        elif selected_provider == "gemini":
            console.print("  Get your key at: https://aistudio.google.com/app/apikey")
        elif selected_provider == "openrouter":
            console.print("  Get your key at: https://openrouter.ai/keys")
        
        console.print()
        api_key = Prompt.ask("API Key", password=True)
        
        if api_key:
            set_api_key(selected_provider, api_key)
            console.print(f"\n[green]✓[/green] API key saved securely\n")
        else:
            console.print("\n[yellow]⚠ Skipped - you can set it later with:[/yellow]")
            console.print(f"  [bold]ados auth set-key {selected_provider}[/bold]\n")
    else:
        console.print("[bold]Step 2: API Key[/bold]\n")
        console.print(f"  [dim]{provider_info['name']} doesn't require an API key![/dim]\n")
        
        if selected_provider == "ollama":
            console.print("  Make sure Ollama is running:")
            console.print("  [bold]ollama serve[/bold]\n")
            
            # Ask for custom URL if using remote Ollama
            if Confirm.ask("Is Ollama running on a different machine?", default=False):
                url = Prompt.ask("Enter the Ollama URL (e.g., http://192.168.1.100:11434/v1)")
                if url:
                    set_base_url(url)
                    console.print(f"[green]✓[/green] Base URL set to {url}\n")
    
    # Step 3: Model selection (optional)
    console.print("[bold]Step 3: Model selection (optional)[/bold]\n")
    console.print(f"  Default model: [cyan]{provider_info['default_model']}[/cyan]")
    
    if Confirm.ask("Use a different model?", default=False):
        model = Prompt.ask("Model name")
        if model:
            set_model(model)
            console.print(f"[green]✓[/green] Model set to {model}\n")
    
    # Done!
    console.print(Panel.fit(
        "[bold green]Setup Complete![/bold green]\n\n"
        "You can now use AutoDevOS:\n"
        "  [bold]ados[/bold]          - Start interactive session\n"
        # "  [bold]ados .[/bold]        - Open current directory\n"
        "  [bold]ados config[/bold]   - View/edit configuration",
        "  [bold]ados --help[/bold]   - Show help information"
        border_style="green",
    ))


@auth.command("setup-token")
@click.argument("token")
def auth_setup_token(token: str):
    """
    Setup from dashboard token.
    
    The token is a base64-encoded JSON with configuration.
    This allows users to copy a single command from the dashboard
    to configure their CLI.
    
    Token format (JSON):
    {
        "provider": "openai",
        "model": "gpt-4o",
        "base_url": "..." (optional)
    }
    
    Note: API keys are NOT included in tokens for security.
    Users must set their own API keys separately.
    """
    try:
        # Decode the token
        decoded = base64.b64decode(token).decode("utf-8")
        config = json.loads(decoded)
    except Exception as e:
        console.print(f"[red]Invalid token: {e}[/red]")
        return
    
    # Apply configuration
    if "provider" in config:
        provider = config["provider"]
        if provider in PROVIDERS:
            set_provider(provider)
            console.print(f"[green]✓[/green] Provider: {provider}")
    
    if "model" in config:
        set_model(config["model"])
        console.print(f"[green]✓[/green] Model: {config['model']}")
    
    if "base_url" in config:
        set_base_url(config["base_url"])
        console.print(f"[green]✓[/green] Base URL: {config['base_url']}")
    
    console.print("\n[green]Configuration applied from token![/green]")
    
    # Remind about API key if needed
    provider = config.get("provider", get_provider())
    if PROVIDERS.get(provider, {}).get("requires_key", False):
        if not get_api_key(provider):
            console.print(f"\n[yellow]⚠ Don't forget to set your API key:[/yellow]")
            console.print(f"  [bold]ados auth set-key {provider}[/bold]")


@auth.command("generate-token")
def auth_generate_token():
    """Generate a setup token for sharing (without API keys)."""
    from autodevos.cli.config_manager import get_full_config
    
    config = get_full_config()
    
    # Remove sensitive data
    token_config = {
        "provider": config["provider"],
        "model": config["model"],
    }
    
    # Only include base_url if it's custom
    provider = config["provider"]
    default_url = PROVIDERS.get(provider, {}).get("default_url")
    if config["base_url"] != default_url:
        token_config["base_url"] = config["base_url"]
    
    # Encode
    token = base64.b64encode(json.dumps(token_config).encode()).decode()
    
    console.print("\n[bold]Setup Token[/bold] (share this with your team):\n")
    console.print(f"[cyan]{token}[/cyan]")
    console.print("\n[dim]Users can apply it with:[/dim]")
    console.print(f"  [bold]ados auth setup-token {token}[/bold]")
    console.print("\n[yellow]Note: API keys are not included for security.[/yellow]")
