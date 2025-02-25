# Agent Foundry Examples

This directory contains examples for using the Agent Foundry runtime.

## Directory Structure

- **hello_world/** - A simple example demonstrating the YAML-based agent configuration with plugin variables
  - `agently.yaml` - The agent configuration file
  - `plugins/hello/__init__.py` - A simple plugin that demonstrates plugin variables
  - `test_plugin.py` - A test script for verifying plugin functionality

## Running Examples

To run the hello_world example:

```bash
# From the root directory
cd agent_runtime_v2/examples/hello_world
python -m agent_runtime_v2.cli.commands run --agent agently.yaml
```

Or test the plugin directly:

```bash
# From the root directory
cd agent_runtime_v2/examples/hello_world
python test_plugin.py
```

## Creating Your Own Agent

To create your own agent:

1. Create a directory for your agent
2. Create an `agently.yaml` file with your agent configuration
3. Create or reference plugins for your agent to use
4. Run your agent with the CLI command: `python -m agent_runtime_v2.cli.commands run --agent agently.yaml`
