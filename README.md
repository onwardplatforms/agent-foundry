# Agent Foundry

A tool for creating and managing AI agents. Agent Foundry provides a simple CLI for creating, managing, and interacting with AI agents.

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
```

### Running an Agent

Start an interactive chat session with an agent:

```bash
foundry run my-agent
```

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
foundry delete my-agent
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
├── tests/                 # Test suite
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

## Future Plans

- [ ] Implement core agent functionality
- [ ] Add agent configuration management
- [ ] Add plugin system
- [ ] Add documentation site
- [ ] Add CI/CD pipeline
- [ ] Add more test coverage
- [ ] Add example agents and use cases
