"""Plugin manager for handling SK plugin installation and loading."""

import importlib
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from semantic_kernel import Kernel


class PluginNotFoundError(Exception):
    """Raised when a plugin cannot be found."""

    pass


class PluginConfig:
    """Configuration for a plugin."""

    def __init__(
        self,
        name: str,
        source: str,
        version: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
    ):
        """Initialize plugin configuration.

        Args:
            name: Name to use for the plugin when loaded
            source: GitHub repository URL or local path to the plugin
            version: Optional version (git tag/commit) to use
            variables: Optional plugin-specific configuration variables
        """
        self.name = name
        self.source = source
        self.version = version
        self.variables = variables or {}

    @property
    def is_github_source(self) -> bool:
        """Check if the source is a GitHub URL."""
        if not self.source:
            return False
        parsed = urlparse(self.source)
        return (
            parsed.netloc == "github.com"
            or parsed.netloc == "raw.githubusercontent.com"
        )

    @property
    def is_local_source(self) -> bool:
        """Check if the source is a local path."""
        return not self.is_github_source


class PluginManager:
    """Manager for SK plugins."""

    def __init__(self, kernel: Kernel, plugins_dir: Path):
        """Initialize plugin manager.

        Args:
            kernel: Semantic Kernel instance to load plugins into
            plugins_dir: Directory where plugins will be installed
        """
        self.kernel = kernel
        self.plugins_dir = plugins_dir
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        # Add plugins directory to Python path if not already there
        plugins_dir_str = str(plugins_dir.resolve())
        if plugins_dir_str not in sys.path:
            sys.path.append(plugins_dir_str)

    def _set_plugin_variables(self, plugin_config: PluginConfig) -> None:
        """Set plugin variables in environment.

        Args:
            plugin_config: Plugin configuration
        """
        for key, value in plugin_config.variables.items():
            # Check if value references an environment variable
            if value.startswith("$"):
                env_var = value[1:]  # Remove $
                value = os.getenv(env_var, "")

            # Set with AGENT_VAR_ prefix
            env_key = f"AGENT_VAR_{key.upper()}"
            os.environ[env_key] = value

    def install_plugin(
        self, plugin_config: PluginConfig, base_dir: Optional[Path] = None
    ) -> None:
        """Install a plugin from its configuration.

        Args:
            plugin_config: Plugin configuration
            base_dir: Optional base directory for resolving relative paths

        Raises:
            FileNotFoundError: If plugin source doesn't exist
        """
        # Resolve source path relative to base_dir if provided
        source_path = (
            Path(plugin_config.source)
            if base_dir is None
            else base_dir / plugin_config.source
        ).resolve()

        if not source_path.exists():
            raise FileNotFoundError(f"Plugin source path not found: {source_path}")

        # Set plugin variables
        self._set_plugin_variables(plugin_config)

    def load_plugin(self, name: str) -> Any:
        """Load a plugin from the plugins directory.

        Args:
            name: Name of the plugin to load

        Returns:
            The loaded plugin instance

        Raises:
            PluginNotFoundError: If plugin cannot be found
            ImportError: If plugin cannot be imported
        """
        try:
            # Import the plugin module
            module = importlib.import_module(name)

            # Look for a class that matches the plugin name
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and attr.__module__ == module.__name__:
                    plugin_class = attr
                    break

            if plugin_class is None:
                raise PluginNotFoundError(f"No plugin class found in module: {name}")

            # Create an instance and register it with the kernel
            plugin_instance = plugin_class()
            return self.kernel.add_plugin(plugin_instance, plugin_name=name)

        except ImportError as e:
            raise PluginNotFoundError(f"Failed to import plugin {name}: {str(e)}")

    def install_and_load_plugins(
        self, plugin_configs: List[PluginConfig], base_dir: Optional[Path] = None
    ) -> None:
        """Install and load multiple plugins.

        Args:
            plugin_configs: List of plugin configurations
            base_dir: Optional base directory for resolving relative paths
        """
        for config in plugin_configs:
            self.install_plugin(config, base_dir)
            self.load_plugin(config.name)
