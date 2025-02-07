"""Plugin manager for handling SK plugin installation and loading."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from semantic_kernel import Kernel


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

    def __init__(self, plugins_dir: Path):
        """Initialize plugin manager.

        Args:
            plugins_dir: Directory where plugins will be installed
        """
        self.plugins_dir = plugins_dir
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

    def _get_plugin_dir(self, plugin_config: PluginConfig) -> Path:
        """Get the directory where a plugin should be installed.

        Args:
            plugin_config: Plugin configuration

        Returns:
            Path to the plugin directory
        """
        # Use plugin name as directory name, replacing invalid chars
        safe_name = re.sub(r"[^\w\-_]", "_", plugin_config.name)
        return self.plugins_dir / safe_name

    def _clone_github_plugin(
        self, plugin_config: PluginConfig, plugin_dir: Path
    ) -> None:
        """Clone a plugin from GitHub.

        Args:
            plugin_config: Plugin configuration
            plugin_dir: Directory to clone into

        Raises:
            subprocess.CalledProcessError: If git clone fails
        """
        # Remove directory if it exists
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)

        # Clone the repository
        cmd = ["git", "clone", plugin_config.source, str(plugin_dir)]
        subprocess.run(cmd, check=True)

        # Checkout specific version if specified
        if plugin_config.version:
            subprocess.run(
                ["git", "checkout", plugin_config.version],
                cwd=plugin_dir,
                check=True,
            )

    def _copy_local_plugin(self, plugin_config: PluginConfig, plugin_dir: Path) -> None:
        """Copy a local plugin.

        Args:
            plugin_config: Plugin configuration
            plugin_dir: Directory to copy into

        Raises:
            FileNotFoundError: If source path doesn't exist
        """
        source_path = Path(plugin_config.source)
        if not source_path.exists():
            raise FileNotFoundError(
                f"Plugin source path not found: {plugin_config.source}"
            )

        # Remove directory if it exists
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)

        # Copy the plugin files
        if source_path.is_dir():
            shutil.copytree(source_path, plugin_dir)
        else:
            # If it's a single file, create dir and copy
            plugin_dir.mkdir(parents=True)
            shutil.copy2(source_path, plugin_dir)

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

    def install_plugin(self, plugin_config: PluginConfig) -> Path:
        """Install a plugin from its configuration.

        Args:
            plugin_config: Plugin configuration

        Returns:
            Path to the installed plugin directory

        Raises:
            ValueError: If plugin source is invalid
            subprocess.CalledProcessError: If git operations fail
            FileNotFoundError: If local source doesn't exist
        """
        plugin_dir = self._get_plugin_dir(plugin_config)

        if plugin_config.is_github_source:
            self._clone_github_plugin(plugin_config, plugin_dir)
        elif plugin_config.is_local_source:
            self._copy_local_plugin(plugin_config, plugin_dir)
        else:
            raise ValueError(
                f"Invalid plugin source: {plugin_config.source}. "
                "Must be a GitHub URL or local path."
            )

        # Set plugin variables
        self._set_plugin_variables(plugin_config)

        return plugin_dir

    def load_plugin(self, plugin_config: PluginConfig, kernel: Kernel) -> None:
        """Load a plugin into the Semantic Kernel.

        Args:
            plugin_config: Plugin configuration
            kernel: Semantic Kernel instance to load the plugin into

        Raises:
            ValueError: If plugin directory doesn't exist or is invalid
        """
        plugin_dir = self._get_plugin_dir(plugin_config)
        if not plugin_dir.exists():
            raise ValueError(
                f"Plugin directory not found: {plugin_dir}. "
                "Run install_plugin first."
            )

        # Import the plugin into SK
        # This assumes the plugin follows SK's plugin structure
        kernel.import_skill_from_directory(plugin_dir, plugin_config.name)

    def install_and_load_plugins(
        self, plugin_configs: List[PluginConfig], kernel: Kernel
    ) -> None:
        """Install and load multiple plugins.

        Args:
            plugin_configs: List of plugin configurations
            kernel: Semantic Kernel instance to load plugins into
        """
        for config in plugin_configs:
            self.install_plugin(config)
            self.load_plugin(config, kernel)
