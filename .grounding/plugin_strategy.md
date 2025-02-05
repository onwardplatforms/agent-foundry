# Plugin Strategy

## Overview

The ODK (Agent Foundry) plugin system follows a convention-over-configuration approach, combining built-in capabilities with dynamically discovered agent-specific plugins. This design emphasizes simplicity, isolation, and extensibility.

## Architecture

### Directory Structure

```
agent_foundry/
├── capabilities/           # Built-in capabilities
│   ├── __init__.py
│   ├── base.py            # Base capability interfaces
│   ├── web_search.py      # Built-in web search capability
│   └── code_interpreter.py # Built-in code interpreter capability
└── agents/
    └── {agent_id}/
        ├── config.json    # Agent configuration (capabilities only)
        └── plugins/       # Auto-discovered plugins directory
            ├── __init__.py
            └── {plugin_name}/
                ├── __init__.py
                └── plugin.py
```

### Key Components

1. **Built-in Capabilities**
   - Core functionalities provided by the framework
   - Examples: WebSearch, CodeInterpreter, GraphConnectors
   - Configured through agent's `config.json`
   - Standardized interface and schema-driven configuration

2. **Agent-Specific Plugins**
   - Located in `.agents/{agent_id}/plugins/`
   - Automatically discovered and loaded
   - Self-documenting through metadata and descriptions
   - Isolated per agent for security and organization

### Configuration

Agent configuration (`config.json`) focuses only on built-in capabilities:

```json
{
  "id": "my-agent",
  "system_prompt": "You are a helpful AI assistant.",
  "provider": {
    "name": "openai",
    "model": "gpt-4"
  },
  "capabilities": [
    {
      "name": "WebSearch",
      "config": {
        "providers": ["google", "duckduckgo"],
        "sites": [
          { "url": "https://docs.python.org" }
        ]
      }
    }
  ]
}
```

### Plugin Implementation

Plugins use a decorator pattern for easy identification:

```python
@plugin
class CustomPlugin:
    """Example custom plugin."""

    name = "custom_plugin"
    description = "Provides custom functionality"

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this plugin provides."""
        return ["custom_search", "data_processing"]

    def get_prompt_description(self) -> str:
        """Return description for LLM context."""
        return """This plugin provides:
                 - custom_search: Search specific data sources
                 - data_processing: Process data in custom formats"""
```

## Plugin Discovery and Loading

The framework automatically discovers and loads plugins:

1. Scans agent's plugins directory
2. Loads Python modules with `plugin.py`
3. Identifies classes with `@plugin` decorator
4. Instantiates plugin objects
5. Adds plugin capabilities to agent's system prompt

## Benefits

1. **Simplicity**
   - No explicit plugin configuration needed
   - Clear convention for plugin location
   - Automatic discovery and loading

2. **Isolation**
   - Each agent's plugins are isolated
   - No cross-agent plugin interference
   - Better security and organization

3. **Extensibility**
   - Easy to add new plugins
   - Plugins can provide multiple capabilities
   - Self-documenting through metadata

4. **Integration**
   - Natural LLM awareness through system prompt
   - Seamless capability invocation
   - Dynamic plugin usage based on context

## Best Practices

1. **Plugin Development**
   - Use the `@plugin` decorator
   - Provide clear capability descriptions
   - Implement proper cleanup methods
   - Document requirements and dependencies

2. **Security**
   - Validate plugin inputs
   - Handle errors gracefully
   - Respect resource limitations
   - Follow principle of least privilege

3. **Performance**
   - Lazy load plugin resources
   - Cache results when appropriate
   - Clean up resources properly
   - Monitor plugin resource usage

## Future Considerations

1. **Plugin Marketplace**
   - Central repository for community plugins
   - Version management
   - Dependency resolution
   - Security scanning

2. **Enhanced Discovery**
   - Hot-reloading of plugins
   - Plugin dependencies
   - Capability negotiation
   - Plugin conflict resolution

3. **Monitoring and Management**
   - Plugin usage metrics
   - Performance monitoring
   - Resource usage tracking
   - Plugin health checks
