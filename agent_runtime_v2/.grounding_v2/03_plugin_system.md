# Plugin System

## Overview
The Plugin System provides a flexible way to extend agent capabilities through pluggable components. Plugins can be loaded from either local directories or remote GitHub repositories, allowing for both local development and community sharing.

## Core Concepts

### 1. Plugin Sources

```python
@dataclass
class PluginSource(ABC):
    @abstractmethod
    def load(self) -> Type[Plugin]:
        """Load the plugin class from this source"""
        pass

@dataclass
class LocalPluginSource(PluginSource):
    path: Path  # Local filesystem path to plugin

    def load(self) -> Type[Plugin]:
        # Load plugin from local path
        pass

@dataclass
class GitHubPluginSource(PluginSource):
    repo_url: str          # e.g. "github.com/user/repo"
    version_tag: str       # e.g. "v1.0.0"
    plugin_path: str       # Path within repo to plugin
    cache_dir: Optional[Path] = None

    def load(self) -> Type[Plugin]:
        # Load plugin from GitHub, using cache
        pass
```

### 2. Plugin Base Classes

```python
class VariableValidation:
    def __init__(self,
                 options: Optional[List[Any]] = None,
                 range: Optional[Tuple[Optional[Any], Optional[Any]]] = None,
                 pattern: Optional[str] = None,
                 error_message: str = None):
        pass

class PluginVariable:
    def __init__(self,
                 name: Optional[str] = None,  # Inferred from class name if None
                 type: Type = str,
                 description: str = "",
                 default: Optional[Any] = None,
                 sensitive: bool = False,
                 validation: Optional[VariableValidation] = None):
        pass

class Plugin:
    name: str  # Can be inferred from class name
    description: str
    plugin_instructions: str  # Plain text instructions for agents
    variables: List[PluginVariable]
```

### 3. Plugin Implementation Example

```python
class WeatherPlugin(Plugin):
    name = "weather"
    description = "Plugin for getting weather information"
    plugin_instructions = """
    Use this plugin to get weather information for cities.
    The temperature will be returned in the configured units.
    """

    api_key = PluginVariable(
        type=str,
        description="API key for weather service",
        sensitive=True
    )
    units = PluginVariable(
        type=str,
        default="celsius",
        validation=VariableValidation(
            options=["celsius", "fahrenheit"]
        )
    )

    @kernel_function(description="Get current weather")
    def get_weather(self, city: str) -> str:
        # Implementation using self.api_key and self.units
        pass
```

## Key Features

1. **Plugin Sources**
   - Local directory plugins with direct filesystem access
   - Remote GitHub plugins with version pinning and caching
   - Built-in system plugins
   - Source abstraction allowing future expansion (GitLab, BitBucket, etc.)

2. **Variable System**
   - Type support including nested types (e.g., List[str])
   - Optional default values
   - Built-in validation
   - Sensitive value handling
   - Runtime configuration of plugin instances

3. **Function Discovery**
   - Automatic discovery of @kernel_function decorated methods
   - Function override priority based on plugin load order
   - Simple function signatures without dependencies

4. **Plugin Instructions**
   - Plain text format
   - Runtime aggregation for agent context
   - No cross-plugin references
   - No versioning required for local plugins

## Implementation Guidelines

1. **Plugin Directory Structure**
   ```
   plugins/
   ├── built_in/         # System provided plugins
   ├── local/            # User's local plugins
   └── remote/           # Cached remote plugins
   ```

2. **Plugin Loading**
   ```python
   # Loading a local plugin
   agent.load_plugin(
       LocalPluginSource("./plugins/weather"),
       variables={
           "api_key": "123",
           "units": "fahrenheit"
       }
   )

   # Loading a GitHub plugin
   agent.load_plugin(
       GitHubPluginSource(
           repo_url="github.com/weather-org/weather-plugin",
           version_tag="v1.0.0",
           plugin_path="weather"
       ),
       variables={
           "api_key": "456",
           "units": "celsius"
       }
   )
   ```

3. **Variable Type System**
   ```python
   # Example of nested type support
   data_list = PluginVariable(
       type=List[str],
       description="List of strings to process"
   )

   config_dict = PluginVariable(
       type=Dict[str, Any],
       description="Configuration dictionary"
   )
   ```

## Security Considerations

1. **Local Plugins**
   - Direct filesystem access
   - No version control needed
   - User responsible for code safety

2. **Remote Plugins**
   - Version pinning required
   - Code verification recommended
   - Cached local copies
   - Isolation between plugin instances

## Best Practices

1. **Plugin Development**
   - Clear, specific plugin instructions
   - Meaningful variable descriptions
   - Appropriate validation rules
   - Single responsibility principle

2. **Plugin Usage**
   - Load order consideration for overrides
   - Careful handling of sensitive variables
   - Clear documentation of requirements
   - Proper version pinning for remote plugins

3. **Error Handling**
   - Graceful plugin load failures
   - Clear validation error messages
   - Proper cleanup on unload
   - Cache management for remote plugins
