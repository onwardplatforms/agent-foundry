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

Or simply:

```bash
# From this directory
agently run
```

Test just the plugin:

```bash
# From this directory
python test_plugin.py
```

## Testing the default_name Variable

To test that the plugin variables are working correctly, try these interactions:

1. For a generic greeting using the default name:
   ```
   You> greet me
   Assistant> Hello, Friend!
   ```

2. For greeting a specific person:
   ```
   You> greet Alice
   Assistant> Hello, Alice!
   ```

3. Explicitly verify the default_name variable:
   ```
   You> use the greet function with default variables
   Assistant> Hello, Friend!
   ```

These interactions confirm that the plugin is correctly using the `default_name` variable set to "Friend" in the YAML configuration.

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
