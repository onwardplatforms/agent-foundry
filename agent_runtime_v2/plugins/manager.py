from typing import Dict, List, Optional, Any, Type
from pathlib import Path
import logging

from ..core import get_error_handler
from ..errors import PluginError, ErrorContext, RetryHandler, RetryConfig
from .base import Plugin
from .sources import PluginSource, LocalPluginSource

logger = logging.getLogger(__name__)


class PluginManager:
    """Manages plugin loading and execution with error handling."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the plugin manager.

        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self.error_handler = get_error_handler()
        self.retry_handler = RetryHandler(
            RetryConfig(max_attempts=2, initial_delay=0.5, max_delay=5.0)
        )
        # Store both the plugin class and instance
        self.plugins: Dict[str, tuple[Type[Plugin], Plugin]] = {}
        logger.info("PluginManager initialized")

    async def _handle_plugin_operation(
        self, operation_name: str, **context_details
    ) -> ErrorContext:
        """Create error context for plugin operations."""
        return ErrorContext(
            component="plugin_manager",
            operation=operation_name,
            details=context_details,
        )

    def _create_plugin_error(
        self,
        message: str,
        context: ErrorContext,
        cause: Exception = None,
        recovery_hint: Optional[str] = None,
    ) -> PluginError:
        """Create a standardized plugin error."""
        return PluginError(
            message=message,
            context=context,
            recovery_hint=recovery_hint
            or "Check plugin configuration and dependencies",
            cause=cause,
        )

    async def load_plugin(
        self, source: PluginSource, variables: Optional[Dict[str, Any]] = None
    ) -> Plugin:
        """Load a plugin with error handling.

        Args:
            source: The plugin source (local or GitHub)
            variables: Optional dictionary of variable values

        Returns:
            The loaded plugin instance

        Raises:
            PluginError: If plugin loading fails
        """
        try:
            context = await self._handle_plugin_operation(
                "load_plugin", source=str(source)
            )
            logger.info(f"Loading plugin from source: {source}")

            # Load the plugin class
            logger.debug("Calling source.load() to get plugin class")
            plugin_class = source.load()
            logger.info(f"Loaded plugin class: {plugin_class.__name__}")

            # Log plugin class details
            logger.info(
                f"Plugin class details: name={plugin_class.name}, description={plugin_class.description}"
            )
            logger.debug(
                f"Plugin variables: {[name for name, _ in plugin_class.__dict__.items() if hasattr(plugin_class, name) and isinstance(getattr(plugin_class, name), type) and name != 'name']}"
            )

            # Create plugin instance with variables
            logger.debug(f"Creating plugin instance with variables: {variables}")
            try:
                plugin_instance = plugin_class(**(variables or {}))
                logger.info(f"Plugin instance created successfully: {plugin_instance}")
            except Exception as e:
                logger.error(f"Error creating plugin instance: {e}", exc_info=e)
                raise

            # Store both class and instance
            self.plugins[plugin_class.name] = (plugin_class, plugin_instance)
            logger.info(f"Plugin {plugin_class.name} stored in plugin manager")

            return plugin_instance

        except Exception as e:
            logger.error(f"Failed to load plugin from source {source}: {e}", exc_info=e)
            raise self._create_plugin_error(
                message=f"Failed to load plugin from source: {source}",
                context=context,
                cause=e,
                recovery_hint="Verify plugin source exists and variables are correct",
            ) from e

    async def execute_plugin(
        self, plugin_name: str, method_name: str, *args, **kwargs
    ) -> Any:
        """Execute a plugin method with error handling and retries."""
        try:
            context = await self._handle_plugin_operation(
                "execute_plugin", plugin_name=plugin_name, method_name=method_name
            )
            logger.info(f"Executing plugin method: {plugin_name}.{method_name}")

            if plugin_name not in self.plugins:
                logger.error(f"Plugin not loaded: {plugin_name}")
                raise KeyError(f"Plugin not loaded: {plugin_name}")

            _, plugin_instance = self.plugins[plugin_name]
            logger.debug(f"Retrieved plugin instance: {plugin_instance}")

            if not hasattr(plugin_instance, method_name):
                logger.error(f"Plugin {plugin_name} has no method {method_name}")
                raise AttributeError(
                    f"Plugin {plugin_name} has no method {method_name}"
                )

            method = getattr(plugin_instance, method_name)
            logger.debug(f"Retrieved method: {method}")

            # Check if method is a kernel function
            if not hasattr(method, "_is_kernel_function"):
                logger.error(f"Method {method_name} is not a kernel function")
                raise ValueError(f"Method {method_name} is not a kernel function")
            logger.debug(f"Confirmed {method_name} is a kernel function")

            async def _execute():
                logger.debug(
                    f"Executing {plugin_name}.{method_name} with args={args}, kwargs={kwargs}"
                )
                # Handle both sync and async methods
                if hasattr(method, "__await__"):
                    result = await method(*args, **kwargs)
                    logger.debug(
                        f"Async method execution completed with result: {result}"
                    )
                    return result
                result = method(*args, **kwargs)
                logger.debug(f"Sync method execution completed with result: {result}")
                return result

            logger.debug(f"Executing {plugin_name}.{method_name} with retry")
            result = await self.retry_handler.execute_with_retry(_execute)
            logger.info(
                f"Execution of {plugin_name}.{method_name} completed successfully"
            )
            return result

        except Exception as e:
            logger.error(
                f"Failed to execute plugin {plugin_name}.{method_name}: {e}", exc_info=e
            )
            raise self._create_plugin_error(
                message=f"Failed to execute plugin {plugin_name}.{method_name}",
                context=context,
                cause=e,
                recovery_hint="Check method exists and arguments are correct",
            ) from e

    async def unload_plugin(self, plugin_name: str) -> None:
        """Unload a plugin with error handling."""
        try:
            context = await self._handle_plugin_operation(
                "unload_plugin", plugin_name=plugin_name
            )
            logger.info(f"Unloading plugin: {plugin_name}")

            if plugin_name not in self.plugins:
                logger.debug(f"Plugin {plugin_name} not found, nothing to unload")
                return

            plugin_class, plugin_instance = self.plugins[plugin_name]
            logger.debug(f"Retrieved plugin instance: {plugin_instance}")

            # Call cleanup if it exists
            if hasattr(plugin_instance, "cleanup"):
                logger.debug(f"Calling cleanup method on plugin {plugin_name}")
                if hasattr(plugin_instance.cleanup, "__await__"):
                    await plugin_instance.cleanup()
                else:
                    plugin_instance.cleanup()
                logger.info(f"Cleanup completed for plugin {plugin_name}")

            del self.plugins[plugin_name]
            logger.info(
                f"Plugin {plugin_name} unloaded and removed from plugin manager"
            )

        except Exception as e:
            logger.error(f"Failed to unload plugin {plugin_name}: {e}", exc_info=e)
            raise self._create_plugin_error(
                message=f"Failed to unload plugin: {plugin_name}",
                context=context,
                cause=e,
            ) from e

    # Convenience method for loading from file path
    async def load_plugin_from_path(
        self, path: str | Path, variables: Optional[Dict[str, Any]] = None
    ) -> Plugin:
        """Load a plugin from a file path.

        Args:
            path: Path to plugin file or directory
            variables: Optional dictionary of variable values

        Returns:
            The loaded plugin instance
        """
        logger.info(f"Loading plugin from path: {path}")
        source = LocalPluginSource(Path(path))
        return await self.load_plugin(source, variables)

    def get_openai_functions(self) -> Dict[str, Any]:
        """Convert registered plugins to OpenAI function definitions.

        Returns:
            Dictionary containing functions list and function_call setting
        """
        logger.debug("Converting plugins to OpenAI function definitions")
        functions = []

        for plugin_class, plugin_instance in self.plugins.values():
            # Get all kernel functions from the plugin
            kernel_functions = plugin_class.get_kernel_functions()
            logger.debug(
                f"Plugin {plugin_instance.name} has {len(kernel_functions)} kernel functions"
            )

            for func_name, func in kernel_functions.items():
                # Convert each function to OpenAI format
                function_def = {
                    "name": f"{plugin_instance.name}_{func_name}",
                    "description": func.__doc__ or "",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                }

                # Get function parameters
                import inspect

                sig = inspect.signature(func)
                for param_name, param in sig.parameters.items():
                    if param_name == "self":
                        continue

                    param_def = {
                        "type": "string",  # Default to string for simplicity
                        "description": "",  # Could be enhanced with docstring parsing
                    }

                    # Mark as required if no default value
                    if param.default == inspect.Parameter.empty:
                        function_def["parameters"]["required"].append(param_name)

                    function_def["parameters"]["properties"][param_name] = param_def

                functions.append(function_def)
                logger.debug(f"Added function definition for {function_def['name']}")

        result = {"functions": functions, "function_call": "auto"}
        logger.info(
            f"Created OpenAI functions definition with {len(functions)} functions"
        )
        return result
