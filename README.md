# Agent Foundry

A tool for creating and managing AI agents. Agent Foundry provides a simple CLI for creating, managing, and interacting with AI agents.

## Features

- 🔄 Real-time streaming responses
- 🎯 Simple configuration-based agent creation
- 🛠️ Multiple LLM provider support
- 📝 Customizable system prompts
- 🔌 Environment-based configuration

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

Create a `.env` file in your project root with your provider-specific API keys and settings:

```bash
# OpenAI Settings
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4  # Optional, defaults to gpt-3.5-turbo

# Ollama Settings (Coming Soon)
OLLAMA_HOST=http://localhost:11434  # Optional
OLLAMA_MODEL=llama2  # Optional
```

## Usage

### Creating an Agent

Create a new agent with an optional name, provider, and system prompt:

```bash
# Create with OpenAI (default)
foundry create my-agent --provider openai --model gpt-4

# Create with Ollama (coming soon)
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
│   ├── agent.py           # Base agent implementation
│   ├── providers/         # Provider implementations
│   │   ├── __init__.py
│   │   ├── base.py       # Provider interfaces
│   │   ├── openai.py     # OpenAI provider
│   │   └── ollama.py     # Ollama provider (coming soon)
│   ├── cli/              # CLI implementation
│   │   ├── __init__.py
│   │   └── commands.py
│   └── constants.py       # Shared constants
├── tests/                 # Test suite (84% coverage)
├── .env                   # Environment variables (not in repo)
└── agents/               # Agent storage directory
    └── my-agent/         # Individual agent directory
        └── config.json   # Agent configuration
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

#### Ollama (Coming Soon)
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

Settings precedence order:
1. Agent config file (highest priority)
2. Environment variables
3. Default values (lowest priority)

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
✅ Real-time streaming responses
✅ Command-line interface
✅ Test suite (84% coverage)
⏳ Ollama provider (in progress)
⏳ Documentation site
⏳ CI/CD pipeline

## Future Plans

- [ ] Complete Ollama provider implementation
- [ ] Add per-agent environment variable support
- [ ] Add more provider implementations (Anthropic, etc.)
- [ ] Add conversation history persistence
- [ ] Add plugin system for custom capabilities
- [ ] Improve test coverage to 90%+
- [ ] Add comprehensive documentation site
