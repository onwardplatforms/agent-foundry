# Agent Foundry

A tool for creating and managing AI agents.

## Overview

Agent Foundry is a command-line tool that helps you create, manage, and interact with AI agents. It provides a simple interface for working with agents powered by semantic kernels.

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/agent-foundry.git
cd agent-foundry

# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`

# Install for development
make install-dev
```

## Usage

Agent Foundry provides several commands for managing agents:

```bash
# Create a new agent
foundry create [NAME]  # NAME is optional, generates random ID if not provided

# Run an interactive session with an agent
foundry run AGENT_ID

# List all available agents
foundry list

# Delete an agent
foundry delete AGENT_ID
```

### Command Options

- `create`
  - `--debug`: Enable debug mode
- `run`
  - `--debug`: Enable debug mode
- `list`
  - `--verbose`: Show detailed information
- `delete`
  - `--force`: Skip confirmation prompt

## Development

Agent Foundry uses modern Python tooling for development:

```bash
# Install development dependencies
make install-dev

# Run tests
make test

# Format code
make format

# Run linters
make lint

# Run type checking
make check

# Run all checks
make all
```

## Project Structure

```
agent_foundry/
    __init__.py              # Package root, version info
    cli/                     # CLI subpackage
        __init__.py          # CLI package init
        commands.py          # CLI command implementations
tests/
    test_cli.py             # CLI tests
```

## Dependencies

- `click`: Command line interface creation
- `semantic-kernel`: AI agent functionality
- `python-dotenv`: Environment variable management
- Development tools:
  - `pytest`: Testing
  - `black`: Code formatting
  - `flake8`: Linting
  - `mypy`: Type checking
  - `isort`: Import sorting

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[Add your chosen license here]

## Future Plans

- [ ] Implement core agent functionality
- [ ] Add agent configuration management
- [ ] Add plugin system
- [ ] Add documentation site
- [ ] Add CI/CD pipeline
- [ ] Add more test coverage
- [ ] Add example agents and use cases
