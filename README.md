# Agent Foundry

A tool for creating and managing AI agents. Agent Foundry provides a simple CLI for creating, managing, and interacting with AI agents.

## Features

- 🔄 Real-time streaming responses
- 🎯 Simple configuration-based agent creation
- 🛠️ Multiple LLM provider support (OpenAI, Ollama)
- 📝 Customizable system prompts
- 🔌 Per-agent environment configuration
- 🌐 Flexible environment variable handling

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/agent-foundry.git
cd agent-foundry

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in editable mode
pip install -e .
```

## Configuration

You can configure environment variables at two levels:

1. Agent-specific: Create a `.env` file in `.agents/<agent_id>/.env`
2. Project-wide: Create a `.env` file in your project root

Environment variables follow a simple waterfall pattern, where more specific settings override more general ones:
1. Agent's `.env` file (highest priority)
2. Agent's `config.json` values
3. Global `.env` file
4. Default values (lowest priority)

Example `.env` files:

```bash
# Project-wide .env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4  # Optional, defaults to gpt-3.5-turbo

# Ollama Settings
OLLAMA_BASE_URL=http://localhost:11434  # Optional
OLLAMA_MODEL=llama2  # Optional
```

```bash
# Agent-specific .env (.agents/my-agent/.env)
OPENAI_MODEL=gpt-4  # Override model just for this agent
OPENAI_API_KEY=agent-specific-key  # Use different API key for this agent
```

This approach allows you to:
- Set default values in your project's root `.env`
- Override settings for specific agents in their `.env` files
- Keep sensitive information (like API keys) separate for different agents

## Usage

### Creating an Agent

Create a new agent with an optional name, provider, and system prompt:

```bash
# Create with OpenAI (default)
python -m agent_foundry create my-agent --provider openai --model gpt-4

# Create with Ollama
python -m agent_foundry create llama-agent --provider ollama --model llama2

# Create with custom system prompt
python -m agent_foundry create my-agent --system-prompt "You are a helpful coding assistant."

# Create with debug mode
python -m agent_foundry create my-agent --debug
```

### Running an Agent

Start an interactive chat session with an agent:

```bash
# Basic run
python -m agent_foundry run my-agent

# Run with debug mode
python -m agent_foundry run my-agent --debug
```

The agent will respond in real-time with streaming output.

### Listing Agents

List all available agents:

```bash
# Basic list
python -m agent_foundry list

# Detailed list with configurations
python -m agent_foundry list --verbose
```

### Deleting an Agent

Delete an agent:

```bash
# With confirmation prompt
python -m agent_foundry delete my-agent

# Force delete without confirmation
python -m agent_foundry delete my-agent --force
```

## Project Structure

```
agent-foundry/
├── agent_foundry/          # Main package
│   ├── __init__.py
│   ├── __main__.py        # Package entry point
│   ├── agent.py           # Agent implementation
│   ├── provider_impl.py   # Provider implementations
│   ├── providers.py       # Provider definitions
│   ├── env.py            # Environment handling
│   ├── cli/              # CLI implementation
│   │   ├── __init__.py
│   │   └── commands.py
│   └── constants.py       # Shared constants
├── tests/                 # Test suite (95% coverage)
├── .env                   # Global environment variables
└── .agents/              # Agent storage directory
    └── my-agent/         # Individual agent directory
        ├── config.json   # Agent configuration
        └── .env          # Agent-specific environment
```

## Agent Configuration

Each agent is defined by a `config.json` file with the following structure:

```json
{
  "id": "my-agent",
  "system_prompt": "You are a helpful AI assistant.",
  "provider": {
    "name": "openai",
    "model": "gpt-4",
    "settings": {
      "temperature": 0.7,
      "top_p": 0.95,
      "max_tokens": 1000
    }
  }
}
```

### Provider Settings

#### OpenAI
```json
{
  "provider": {
    "name": "openai",
    "model": "gpt-4",  // Optional, falls back to AGENT_FOUNDRY_OPENAI_MODEL, OPENAI_MODEL, or gpt-3.5-turbo
    "settings": {
      "temperature": 0.7,    // Optional, default: 0.7
      "top_p": 1.0,         // Optional, default: 1.0
      "max_tokens": 1000    // Optional, default: 1000
    }
  }
}
```

#### Ollama
```json
{
  "provider": {
    "name": "ollama",
    "model": "llama2",  // Optional, falls back to AGENT_FOUNDRY_OLLAMA_MODEL, OLLAMA_MODEL, or llama2
    "settings": {
      "temperature": 0.7,      // Optional, default: 0.7
      "base_url": "http://localhost:11434"  // Optional, falls back to AGENT_FOUNDRY_OLLAMA_BASE_URL, OLLAMA_BASE_URL, or default
    }
  }
}
```

### Environment Variables

Settings precedence order (highest to lowest):
1. Agent-specific environment variables (AGENT_FOUNDRY_*)
2. Global environment variables
3. Configuration file values
4. Default values

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
make test

# Run linting and type checking
make lint

# Run all checks
make all
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Project Status

✅ Core agent functionality
✅ OpenAI provider implementation
✅ Ollama provider implementation
✅ Real-time streaming responses
✅ Command-line interface
✅ Per-agent environment variables
✅ Test suite (95% coverage)
✅ Robust environment variable handling
⏳ Documentation site
⏳ CI/CD pipeline

## Future Plans

- [ ] Add more provider implementations (Anthropic, etc.)
- [ ] Add conversation history persistence
- [ ] Add plugin system for custom capabilities
- [ ] Add comprehensive documentation site
- [ ] Add support for function calling
- [ ] Add support for tool usage
