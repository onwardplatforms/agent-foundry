"""Plugin manager for handling SK plugin installation and loading."""

import importlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from semantic_kernel import Kernel


class PluginNotFoundError(Exception):
    """Raised when a plugin cannot be found."""

    pass


class PluginConfig:
    """Configuration for a plugin."""

    def __init__(
        self,
        source: str,
        version: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
    ):
        """Initialize plugin configuration.

        Args:
            source: GitHub repository URL or local path to the plugin
            version: Optional version (git tag/commit) to use, required for GitHub sources  # noqa: E501
            variables: Optional plugin-specific configuration variables

        Raises:
            ValueError: If version is not provided for GitHub sources or if version is provided for local sources  # noqa: E501
        """
        self.source = source
        self.variables = variables or {}

        # Validate version requirement for GitHub sources
        if self.is_github_source and not version:
            raise ValueError("Version must be specified for GitHub plugins")
        if not self.is_github_source and version:
            raise ValueError("Version cannot be specified for local plugins")
        self.version = version

    @property
    def name(self) -> str:
        """Get the plugin name derived from the source path."""
        if self.is_github_source:
            # Extract repo name from GitHub URL and sanitize
            parts = self.source.split("/")
            raw_name = parts[-1]
        else:
            # Use last part of local path and sanitize
            raw_name = Path(self.source).name

        # Replace hyphens with underscores and remove any other invalid characters
        return re.sub(r"[^0-9A-Za-z_]", "_", raw_name)

    @property
    def is_github_source(self) -> bool:
        """Check if the source is a GitHub URL."""
        if not self.source:
            return False
        return self.source.startswith("https://github.com/") or self.source.startswith(
            "github.com/"
        )

    @property
    def is_local_source(self) -> bool:
        """Check if the source is a local path."""
        return not self.is_github_source


class PluginManager:
    """Manager for SK plugins."""

    PLUGINS_DIR = ".plugins"  # Hidden directory for installed plugins

    def __init__(self, kernel: Kernel, base_dir: Path):
        """Initialize plugin manager.

        Args:
            kernel: Semantic Kernel instance to load plugins into
            base_dir: Base directory where .plugins directory will be created
        """
        self.kernel = kernel
        self.plugins_dir = base_dir / self.PLUGINS_DIR
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        # Add plugins directory to Python path if not already there
        plugins_dir_str = str(self.plugins_dir.resolve())
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

    def _clone_github_plugin(self, plugin_config: PluginConfig) -> Path:
        """Clone a plugin from GitHub.

        Args:
            plugin_config: Plugin configuration

        Returns:
            Path to the cloned repository

        Raises:
            subprocess.CalledProcessError: If git clone fails
            AssertionError: If version is None (should never happen due to PluginConfig validation)
        """
        # Version should never be None for GitHub plugins (validated in PluginConfig)
        assert (
            plugin_config.version is not None
        ), "Version must be specified for GitHub plugins"

        # Create base plugin directory: .plugins/name
        plugin_base = self.plugins_dir / plugin_config.name
        if plugin_base.exists():
            shutil.rmtree(plugin_base)
        plugin_base.mkdir(parents=True, exist_ok=True)

        # Clone into a temporary directory
        temp_dir = plugin_base / "temp"
        # Handle URLs that already include https://
        clone_url = (
            plugin_config.source
            if plugin_config.source.startswith("https://")
            else f"https://{plugin_config.source}"
        )
        subprocess.run(
            ["git", "clone", clone_url, str(temp_dir)],
            check=True,
        )

        # Checkout specific version
        subprocess.run(
            ["git", "checkout", plugin_config.version],
            cwd=temp_dir,
            check=True,
        )

        # Create the versioned directory and move files
        version_dir = plugin_base / plugin_config.version
        if version_dir.exists():
            shutil.rmtree(version_dir)
        version_dir.mkdir(exist_ok=True)

        # Move all files from temp directory to version directory
        for item in temp_dir.iterdir():
            if item.name != ".git":  # Skip .git directory
                if item.is_dir():
                    shutil.copytree(item, version_dir / item.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, version_dir / item.name)

        # Clean up temp directory
        shutil.rmtree(temp_dir)

        return version_dir

    def install_plugin(
        self, plugin_config: PluginConfig, base_dir: Optional[Path] = None
    ) -> None:
        """Install a plugin from its configuration.

        Args:
            plugin_config: Plugin configuration
            base_dir: Optional base directory for resolving relative paths

        Raises:
            FileNotFoundError: If plugin source doesn't exist
            subprocess.CalledProcessError: If git operations fail
            ValueError: If version is not provided for GitHub sources  # noqa: E501
        """
        if plugin_config.is_github_source:
            # Install GitHub plugin
            plugin_dir = self._clone_github_plugin(plugin_config)
            # Add plugin directory to Python path
            plugin_base = str(self.plugins_dir / plugin_config.name)
            if plugin_base not in sys.path:
                sys.path.append(plugin_base)
        else:
            # Handle local source - can be anywhere, just resolve the path
            source_path = (
                Path(plugin_config.source)
                if base_dir is None
                else base_dir / plugin_config.source
            ).resolve()

            if not source_path.exists():
                raise FileNotFoundError(f"Plugin source path not found: {source_path}")

            # Create plugin directory and copy files
            plugin_dir = self.plugins_dir / plugin_config.name
            if plugin_dir.exists():
                shutil.rmtree(plugin_dir)
            plugin_dir.mkdir(parents=True, exist_ok=True)

            # Copy all files from source to plugin directory
            for item in source_path.iterdir():
                if item.is_dir():
                    shutil.copytree(item, plugin_dir / item.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, plugin_dir / item.name)

            # Add plugin directory to Python path
            if str(plugin_dir) not in sys.path:
                sys.path.append(str(plugin_dir))

        # Set plugin variables
        self._set_plugin_variables(plugin_config)

    def load_plugin(self, name: str, version: Optional[str] = None) -> Any:
        """Load a plugin from the plugins directory.

        Args:
            name: Name of the plugin to load
            version: Version to load for GitHub plugins

        Returns:
            The loaded plugin instance

        Raises:
            PluginNotFoundError: If plugin cannot be found
            ImportError: If plugin cannot be imported  # noqa: E501
        """
        try:
            # For GitHub plugins, import from versioned directory
            if version:
                module_path = f"{name}.{version}"
                module = importlib.import_module(module_path)
            else:
                # For local plugins, try importing plugin.py directly
                plugin_dir = self.plugins_dir / name
                if not plugin_dir.exists():
                    raise PluginNotFoundError(
                        f"Plugin directory not found: {plugin_dir}"
                    )

                # Try plugin.py first, then __init__.py
                if (plugin_dir / "plugin.py").exists():
                    module = importlib.import_module("plugin")
                elif (plugin_dir / "__init__.py").exists():
                    module = importlib.import_module(name)
                else:
                    raise PluginNotFoundError(
                        f"Neither plugin.py nor __init__.py found in {plugin_dir}"
                    )

            # Look for a class that matches the plugin name or is named Plugin/TestPlugin/ExamplePlugin  # noqa: E501
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and attr.__module__ == module.__name__
                    and (
                        attr.__name__ == "Plugin"
                        or attr.__name__ == "TestPlugin"
                        or attr.__name__ == "ExamplePlugin"
                        or attr.__name__.lower() == name.lower()
                    )
                ):
                    plugin_class = attr
                    break

            if plugin_class is None:
                raise PluginNotFoundError(
                    f"No plugin class found in module: {module.__name__}"
                )

            # Create an instance and register it with the kernel
            plugin_instance = plugin_class()
            return self.kernel.add_plugin(plugin_instance, plugin_name=name)

        except ImportError as e:
            raise PluginNotFoundError(
                f"Failed to import plugin {name}: {str(e)}"
            ) from e

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
            # Pass version for GitHub plugins
            version = config.version if config.is_github_source else None
            self.load_plugin(config.name, version)
