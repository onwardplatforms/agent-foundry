# Hello World Example

This example demonstrates a simple agent with plugin variables using the YAML-based configuration approach.

## Structure

- `agently.yaml` - The agent configuration file specifying the model, system prompt, and plugin with variables
- `plugins/hello/__init__.py` - A simple plugin that demonstrates the use of plugin variables
- `test_plugin.py` - A script to test the plugin functionality directly

## The Plugin

The HelloPlugin demonstrates:
- Defining a plugin with a descriptive name and instructions
- Using plugin variables with defaults (`default_name`)
- A simple greeting function that uses the variable

## Running the Example

Run the agent with the CLI:

```bash
# From this directory
python -m agent_runtime_v2.cli.commands run --agent agently.yaml
```

Test just the plugin:

```bash
# From this directory
python test_plugin.py
```

## Customizing

You can customize the `default_name` variable by changing it in the `agently.yaml` file:

```yaml
plugins:
  - source:
      type: "local"
      path: "./plugins/hello"
    variables:
      default_name: "Your Custom Default Name"
```
