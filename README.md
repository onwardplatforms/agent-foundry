# Agent Foundry

A tool for creating and managing AI agents. Agent Foundry provides a simple CLI for creating, managing, and interacting with AI agents.

## Features

- 🔄 Real-time streaming responses
- 🎯 Simple configuration-based agent creation
- 🛠️ Debug mode for troubleshooting
- 📝 Customizable system prompts
- 🔌 Plugin system (planned)

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

Create a `.env` file in your project root with your OpenAI API key:

```bash
OPENAI_API_KEY=your_api_key_here
```

## Usage

### Creating an Agent

Create a new agent with an optional name and system prompt:

```bash
# Create with random ID
foundry create

# Create with specific name
foundry create my-agent

# Create with custom system prompt
foundry create my-agent --system-prompt "You are a helpful coding assistant who specializes in Python."

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

The agent will respond in real-time with streaming output, making the interaction feel more natural and immediate.

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
│   ├── cli/               # CLI implementation
│   │   ├── __init__.py
│   │   └── commands.py
│   └── constants.py       # Shared constants
├── tests/                 # Test suite (87% coverage)
├── .env                   # Environment variables (not in repo)
└── agents/               # Agent storage directory
    └── my-agent/         # Individual agent directory
        └── config.json   # Agent configuration
```

## Architecture and Design Philosophy

Agent Foundry follows a hybrid approach to agent design, balancing simplicity with extensibility:

### Core Principles

1. **Declarative First**: Agents are primarily defined through configuration rather than code
   - Simple JSON configuration files
   - Easy to share and version control
   - Lower barrier to entry

2. **Plugin System** (Planned): Extensibility through a plugin architecture
   - Core functionality in the foundry runtime
   - Users can extend capabilities through plugins
   - Plugins can be shared and reused

3. **Real-time Interaction**: Streaming responses for natural conversation
   - Token-by-token output
   - Immediate feedback
   - Better user experience

### Agent Structure

#### Basic Agent (Current)
```
agents/my-agent/
└── config.json           # Agent configuration
    ├── id               # Unique identifier
    ├── model           # AI model to use
    └── system_prompt   # Agent's personality/role
```

#### Extended Agent (Planned)
```
agents/my-agent/
├── config.json         # Basic configuration
└── plugins/           # Optional plugin directory
    └── custom/        # Custom plugin implementations
```

### Design Decisions

1. **Configuration Over Code**
   - Agents are primarily configuration files
   - Behavior is controlled by the foundry runtime
   - Easy to share and version control

2. **Extensible Runtime**
   - Core functionality in the foundry
   - Plugin system for custom capabilities
   - Clean separation of concerns

3. **Progressive Complexity**
   - Start with simple configuration
   - Add plugins as needed
   - No need to write code for basic use cases

4. **Streaming First**
   - Real-time responses by default
   - Better user experience
   - More natural interaction

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
✅ Basic agent configuration
✅ Real-time streaming responses
✅ Command-line interface
✅ Test suite (87% coverage)
⏳ Plugin system (in progress)
⏳ Documentation site
⏳ CI/CD pipeline
⏳ Example agents and use cases

## Future Plans

- [ ] Complete plugin system implementation
- [ ] Add more example agents and use cases
- [ ] Improve test coverage to 90%+
- [ ] Add comprehensive documentation site
- [ ] Set up CI/CD pipeline
- [ ] Add support for more LLM providers
- [ ] Implement agent memory and persistence
