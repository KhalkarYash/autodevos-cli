# AutoDevOS CLI

AI-powered coding assistant for your terminal — like Claude Code.

## Installation

### Quick Install (Recommended)

```bash
# Using pip
pip install autodevos-cli

# Or using pipx (isolated environment)
pipx install autodevos-cli
```

### From Source

```bash
git clone https://github.com/KhalkarYash/autodevos-cli.git
cd autodevos-cli
pip install -e .
```

## Quick Start

### 1. Setup (First Time)

```bash
# Interactive setup wizard
ados auth setup
```

This will guide you through:
- Choosing your LLM provider (OpenAI, Claude, Gemini, Ollama, etc.)
- Setting up your API key
- Configuring your preferred model

### 2. Start Coding

```bash
# Open in current directory
ados

# Open a specific project
ados ~/projects/myapp

# Run a single command
ados "create a simple todo app with React"
```

## Supported Providers

| Provider | API Key | Default Model |
|----------|---------|---------------|
| `ollama` | Not needed | llama3.2 |
| `openai` | Required | gpt-4o |
| `anthropic` | Required | claude-sonnet-4-20250514 |
| `gemini` | Required | gemini-1.5-pro |
| `openrouter` | Required | anthropic/claude-sonnet-4-20250514 |

## Commands

### Main Commands

```bash
ados                    # Interactive session in current directory
ados <directory>        # Open specific directory
ados "prompt"           # Single prompt mode
ados --init             # Initialize project config
```

### Configuration

```bash
ados config             # Show current config
ados config provider    # List/set provider
ados config model       # Set model
ados config url         # Set custom API URL
ados config providers   # List all providers
```

### Authentication

```bash
ados auth               # Show auth status
ados auth setup         # Interactive setup wizard
ados auth set-key <provider>  # Set API key
ados auth remove-key <provider>  # Remove API key
```

### Session Commands (Interactive Mode)

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/config` | Show current configuration |
| `/tools` | List available tools |
| `/stats` | Show session statistics |
| `/save` | Save current session |
| `/clear` | Clear conversation |
| `/exit` | Exit the session |

## Configuration

### Global Config

Located at `~/.config/autodevos/config.toml`:

```toml
[model]
provider = "anthropic"
name = "claude-sonnet-4-20250514"
temperature = 1.0
```

### Project Config

Create `.autodevos/config.toml` in your project:

```toml
# Project-specific AI instructions
developer_instructions = """
This is a Python FastAPI project.
Follow PEP 8 style guidelines.
Use pytest for testing.
"""

# Tool restrictions
allowed_tools = ["read_file", "write_file", "shell", "grep"]

# Approval policy
approval = "auto"
```

## Team Setup (Dashboard Integration)

For teams, admins can generate a setup token:

```bash
# Admin generates token
ados auth generate-token
# Output: eyJwcm92aWRlci...

# Team members apply it
ados auth setup-token eyJwcm92aWRlci...
ados auth set-key anthropic  # Set their own API key
```

## Using with Ollama (Local)

```bash
# Start Ollama
ollama serve

# Configure AutoDevOS
ados config provider ollama
ados config model llama3.2

# Start coding!
ados
```

### Remote Ollama (Different Machine)

```bash
# On the machine running Ollama:
OLLAMA_HOST=0.0.0.0 ollama serve

# On your machine:
ados config provider ollama
ados config url http://192.168.1.100:11434/v1
```

## Features

- **Multi-Provider Support**: OpenAI, Anthropic, Google, Ollama, and more
- **Interactive Terminal UI**: Rich formatting with streaming responses
- **Built-in Tools**: File operations, shell commands, web search, and more
- **Context Management**: Automatic compression for long conversations
- **Session Persistence**: Save and resume conversations
- **Safety Controls**: Approval policies for dangerous operations
- **MCP Integration**: Extend with Model Context Protocol servers
- **Project Config**: Customize AI behavior per-project

## Environment Variables

Override config with environment variables:

```bash
export API_KEY="your-api-key"
export BASE_URL="https://custom-api.example.com/v1"
```

## Requirements

- Python 3.11+
- For Ollama: Ollama installed and running

## License

MIT
