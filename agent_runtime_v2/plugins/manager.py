from typing import Dict, List, Optional, Any
import importlib.util
import sys
import os

from ..core import get_error_handler
from ..errors import PluginError, ErrorContext, RetryHandler, RetryConfig


class PluginManager:
    """Manages plugin loading and execution with error handling"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.error_handler = get_error_handler()
        self.retry_handler = RetryHandler(
            RetryConfig(max_attempts=2, initial_delay=0.5, max_delay=5.0)
        )
        self.plugins: Dict[str, Any] = {}

    async def _handle_plugin_operation(
        self, operation_name: str, **context_details
    ) -> ErrorContext:
        """Create error context for plugin operations"""
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
        """Create a standardized plugin error"""
        return PluginError(
            message=message,
            context=context,
            recovery_hint=recovery_hint
            or "Check plugin configuration and dependencies",
            cause=cause,
        )

    async def load_plugin(self, plugin_path: str) -> Any:
        """Load a plugin with error handling"""
        try:
            context = await self._handle_plugin_operation(
                "load_plugin", plugin_path=plugin_path
            )

            if not os.path.exists(plugin_path):
                raise FileNotFoundError(f"Plugin file not found: {plugin_path}")

            plugin_name = os.path.splitext(os.path.basename(plugin_path))[0]

            if plugin_name in self.plugins:
                return self.plugins[plugin_name]

            spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
            if not spec or not spec.loader:
                raise ImportError(f"Could not load plugin spec: {plugin_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[plugin_name] = module
            spec.loader.exec_module(module)

            if not hasattr(module, "setup"):
                raise AttributeError(f"Plugin {plugin_name} missing setup function")

            plugin = module.setup()
            self.plugins[plugin_name] = plugin
            return plugin

        except Exception as e:
            raise self._create_plugin_error(
                message=f"Failed to load plugin: {plugin_path}",
                context=context,
                cause=e,
                recovery_hint="Verify plugin file exists and has correct format",
            ) from e

    async def execute_plugin(
        self, plugin_name: str, method_name: str, *args, **kwargs
    ) -> Any:
        """Execute a plugin method with error handling"""
        try:
            context = await self._handle_plugin_operation(
                "execute_plugin", plugin_name=plugin_name, method_name=method_name
            )

            if plugin_name not in self.plugins:
                raise KeyError(f"Plugin not loaded: {plugin_name}")

            plugin = self.plugins[plugin_name]

            if not hasattr(plugin, method_name):
                raise AttributeError(
                    f"Plugin {plugin_name} has no method {method_name}"
                )

            method = getattr(plugin, method_name)

            async def _execute():
                return await method(*args, **kwargs)

            return await self.retry_handler.execute_with_retry(_execute)

        except Exception as e:
            raise self._create_plugin_error(
                message=f"Failed to execute plugin {plugin_name}.{method_name}",
                context=context,
                cause=e,
                recovery_hint="Check plugin method exists and arguments are correct",
            ) from e

    async def unload_plugin(self, plugin_name: str) -> None:
        """Unload a plugin with error handling"""
        try:
            context = await self._handle_plugin_operation(
                "unload_plugin", plugin_name=plugin_name
            )

            if plugin_name not in self.plugins:
                return

            plugin = self.plugins[plugin_name]

            if hasattr(plugin, "cleanup"):
                await plugin.cleanup()

            del self.plugins[plugin_name]
            if plugin_name in sys.modules:
                del sys.modules[plugin_name]

        except Exception as e:
            raise self._create_plugin_error(
                message=f"Failed to unload plugin: {plugin_name}",
                context=context,
                cause=e,
            ) from e
