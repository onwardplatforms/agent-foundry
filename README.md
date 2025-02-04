# Agent Foundry

A tool for creating and managing AI agents. Agent Foundry provides a simple CLI for creating, managing, and interacting with AI agents.

## Features

- 🔄 Real-time streaming responses
- 🎯 Simple configuration-based agent creation
- 🛠️ Multiple LLM provider support (OpenAI, Ollama)
- 📝 Customizable system prompts
- 🔌 Per-agent environment configuration

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

1. Project-wide: Create a `.env` file in your project root
2. Per-agent: Create a `.env` file in `.agents/<agent_id>/.env`

Example `.env` files:

```bash
# Project-wide .env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4  # Optional, defaults to gpt-3.5-turbo

# Ollama Settings
OLLAMA_HOST=http://localhost:11434  # Optional
OLLAMA_MODEL=llama2  # Optional
```

```bash
# Per-agent .env (.agents/my-agent/.env)
OPENAI_MODEL=gpt-4  # Override model just for this agent
```

## Usage

### Creating an Agent

Create a new agent with an optional name, provider, and system prompt:

```bash
# Create with OpenAI (default)
foundry create my-agent --provider openai --model gpt-4

# Create with Ollama
foundry create llama-agent --provider ollama --model llama2

# Create with custom system prompt
foundry create my-agent --system-prompt "You are a helpful coding assistant."

# Create with debug mode
foundry create my-agent --debug
```

### Running an Agent

Start an interactive chat session with an agent:

```bash
# Basic run
foundry run my-agent

# Run with debug mode
foundry run my-agent --debug
```

The agent will respond in real-time with streaming output.

### Listing Agents

List all available agents:

```bash
# Basic list
foundry list

# Detailed list with configurations
foundry list --verbose
```

### Deleting an Agent

Delete an agent:

```bash
# With confirmation prompt
foundry delete my-agent

# Force delete without confirmation
foundry delete my-agent --force
```

## Project Structure

```
agent-foundry/
├── agent_foundry/          # Main package
│   ├── __init__.py
│   ├── agent.py           # Agent implementation
│   ├── provider_impl.py   # Provider implementations
│   ├── providers.py       # Provider definitions
│   ├── env.py            # Environment handling
│   ├── cli/              # CLI implementation
│   │   ├── __init__.py
│   │   └── commands.py
│   └── constants.py       # Shared constants
├── tests/                 # Test suite (83% coverage)
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
    "model": "gpt-4",  // Optional, falls back to OPENAI_MODEL or gpt-3.5-turbo
    "settings": {
      "temperature": 0.7,    // Optional, default: 0.7
      "top_p": 0.95,        // Optional, default: 0.95
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
    "model": "llama2",  // Optional, falls back to OLLAMA_MODEL or llama2
    "settings": {
      "temperature": 0.7,      // Optional, default: 0.7
      "base_url": "http://localhost:11434",  // Optional
      "context_window": 4096   // Optional, default: 4096
    }
  }
}
```

### Environment Variables

Settings precedence order (highest to lowest):
1. System environment variables
2. Agent-specific `.env` file (if exists)
3. Project-wide `.env` file
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
✅ Test suite (83% coverage)
⏳ Documentation site
⏳ CI/CD pipeline

## Future Plans

- [ ] Add more provider implementations (Anthropic, etc.)
- [ ] Add conversation history persistence
- [ ] Add plugin system for custom capabilities
- [ ] Improve test coverage to 90%+
- [ ] Add comprehensive documentation site
