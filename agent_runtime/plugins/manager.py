"""Plugin manager for handling SK plugin installation and loading."""

import importlib
import logging
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
        branch: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
    ):
        """Initialize plugin configuration.

        Args:
            source: GitHub repository URL or local path to the plugin
            version: Optional version (git tag/commit) to use, cannot be used with branch
            branch: Optional branch to use, cannot be used with version
            variables: Optional plugin-specific configuration variables

        Raises:
            ValueError: If both version and branch are specified, or if version/branch is provided for local sources
        """
        self.source = source
        self.variables = variables or {}

        # Validate version/branch requirements for GitHub sources
        if self.is_github_source:
            if version and branch:
                raise ValueError("Cannot specify both version and branch for a plugin.")
            if not version and not branch:
                # Default to main branch if neither is specified
                branch = "main"
        else:
            if version or branch:
                raise ValueError(
                    "Version/branch cannot be specified for local plugins."
                )

        self.version = version
        self.branch = branch

    @property
    def name(self) -> str:
        """Get the plugin name derived from the source path."""
        if self.is_github_source:
            # Extract repo name from GitHub URL and sanitize
            parts = self.source.rstrip("/").split("/")
            raw_name = parts[-1] if parts else "unknown_plugin"
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

    @property
    def git_ref(self) -> str:
        """Get the git reference (version or branch) to use."""
        if not self.is_github_source:
            raise ValueError("git_ref is only valid for GitHub sources.")
        # Should never be None due to init logic
        return self.version or self.branch or "main"


class PluginManager:
    """Manager for SK plugins."""

    PLUGINS_DIR = ".plugins"  # Hidden directory for installed plugins

    def __init__(self, kernel: Kernel, base_dir: Path):
        """Initialize plugin manager.

        Args:
            kernel: Semantic Kernel instance to load plugins into
            base_dir: Base directory where .plugins directory will be created
        """
        self.logger = logging.getLogger(__name__)
        self.kernel = kernel
        self.plugins_dir = base_dir / self.PLUGINS_DIR
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        # Add plugins directory to Python path if not already there
        plugins_dir_str = str(self.plugins_dir.resolve())
        if plugins_dir_str not in sys.path:
            sys.path.append(plugins_dir_str)
            self.logger.debug(
                "Added plugins directory to sys.path: %s", plugins_dir_str
            )

    def _set_plugin_variables(self, plugin_config: PluginConfig) -> None:
        """Set plugin variables in environment.

        Args:
            plugin_config: Plugin configuration
        """
        for key, value in plugin_config.variables.items():
            # Check if value references an environment variable
            if value.startswith("$"):
                env_var = value[1:]  # Remove '$'
                resolved = os.getenv(env_var, "")
                if not resolved:
                    self.logger.warning(
                        "Environment variable '%s' not found for plugin variable '%s'. Using empty string.",
                        env_var,
                        key,
                    )
                value = resolved

            # Set with AGENT_VAR_ prefix
            env_key = f"AGENT_VAR_{key.upper()}"
            os.environ[env_key] = value
            self.logger.debug(
                "Set environment variable '%s' for plugin '%s': '%s'",
                env_key,
                plugin_config.name,
                value,
            )

    def _clone_github_plugin(self, plugin_config: PluginConfig) -> Path:
        """Clone a plugin from GitHub.

        Args:
            plugin_config: Plugin configuration

        Returns:
            Path to the cloned repository

        Raises:
            subprocess.CalledProcessError: If git operations fail
        """
        self.logger.info("Cloning GitHub plugin from '%s'.", plugin_config.source)
        plugin_base = self.plugins_dir / plugin_config.name
        if plugin_base.exists():
            self.logger.debug("Removing existing directory: %s", plugin_base)
            shutil.rmtree(plugin_base)
        plugin_base.mkdir(parents=True, exist_ok=True)

        temp_dir = plugin_base / "temp"

        # Ensure we have a clone URL with https://
        clone_url = (
            plugin_config.source
            if plugin_config.source.startswith("https://")
            else f"https://{plugin_config.source}"
        )
        self.logger.debug("Git clone URL: %s", clone_url)

        subprocess.run(["git", "clone", clone_url, str(temp_dir)], check=True)

        git_ref = plugin_config.git_ref
        self.logger.info(
            "Checking out ref '%s' for plugin '%s'.", git_ref, plugin_config.name
        )

        # Attempt direct checkout
        if plugin_config.version:
            try:
                subprocess.run(["git", "checkout", git_ref], cwd=temp_dir, check=True)
            except subprocess.CalledProcessError as e:
                # If that fails, try with 'v' prefix if not already present
                if not git_ref.startswith("v"):
                    v_ref = f"v{git_ref}"
                    self.logger.warning(
                        "Checkout '%s' failed. Trying 'v%s' instead.", git_ref, git_ref
                    )
                    try:
                        subprocess.run(
                            ["git", "checkout", v_ref], cwd=temp_dir, check=True
                        )
                        git_ref = v_ref  # Update to reflect new ref
                    except subprocess.CalledProcessError:
                        self.logger.error(
                            "git checkout failed for both '%s' and '%s'.",
                            git_ref,
                            v_ref,
                        )
                        raise e
                else:
                    self.logger.error("git checkout failed for ref '%s'.", git_ref)
                    raise e
        else:
            # If branch-based or default main
            subprocess.run(["git", "checkout", git_ref], cwd=temp_dir, check=True)

        # Create a Python-safe version of the git ref for the directory name
        safe_ref = git_ref.replace(".", "_")
        if safe_ref.startswith("v"):
            safe_ref = safe_ref[1:]  # Remove 'v' prefix for module name

        version_dir = plugin_base / safe_ref
        if version_dir.exists():
            self.logger.debug("Removing existing version directory: %s", version_dir)
            shutil.rmtree(version_dir)
        version_dir.mkdir(exist_ok=True)

        # Move all files from temp directory to version directory
        for item in temp_dir.iterdir():
            if item.name == ".git":
                continue  # Skip .git
            dest = version_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

        # Clean up temp dir
        shutil.rmtree(temp_dir)
        self.logger.info(
            "Cloned plugin '%s' to directory: %s", plugin_config.name, version_dir
        )
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
        """
        self.logger.info(
            "Installing plugin '%s' from source '%s'.",
            plugin_config.name,
            plugin_config.source,
        )

        if plugin_config.is_github_source:
            plugin_dir = self._clone_github_plugin(plugin_config)
            plugin_base = str(self.plugins_dir / plugin_config.name)
            if plugin_base not in sys.path:
                sys.path.append(plugin_base)
                self.logger.debug("Added plugin directory to sys.path: %s", plugin_base)
        else:
            # Handle local source
            source_path = (
                Path(plugin_config.source)
                if base_dir is None
                else (base_dir / plugin_config.source)
            ).resolve()

            if not source_path.exists():
                self.logger.error("Local plugin source not found: %s", source_path)
                raise FileNotFoundError(f"Plugin source path not found: {source_path}")

            plugin_dir = self.plugins_dir / plugin_config.name
            if plugin_dir.exists():
                self.logger.debug("Removing existing plugin directory: %s", plugin_dir)
                shutil.rmtree(plugin_dir)
            plugin_dir.mkdir(parents=True, exist_ok=True)

            self.logger.debug(
                "Copying local plugin files from '%s' to '%s'.", source_path, plugin_dir
            )
            for item in source_path.iterdir():
                dest = plugin_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)

            if str(plugin_dir) not in sys.path:
                sys.path.append(str(plugin_dir))
                self.logger.debug(
                    "Added local plugin directory to sys.path: %s", plugin_dir
                )

        self.logger.debug(
            "Setting plugin variables (if any) for '%s'.", plugin_config.name
        )
        self._set_plugin_variables(plugin_config)
        self.logger.info("Plugin '%s' installed successfully!", plugin_config.name)

    def load_plugin(self, name: str, git_ref: Optional[str] = None) -> Any:
        """Load a plugin from the plugins directory.

        Args:
            name: Name of the plugin to load
            git_ref: Git reference (version or branch) for GitHub plugins

        Returns:
            The loaded plugin instance

        Raises:
            PluginNotFoundError: If plugin cannot be found
            ImportError: If plugin cannot be imported
        """
        self.logger.info(
            "Loading plugin '%s' (ref='%s').", name, git_ref if git_ref else "local"
        )
        try:
            module = None
            if git_ref:
                # For GitHub plugins, import from versioned directory
                safe_ref = git_ref.replace(".", "_")
                if safe_ref.startswith("v"):
                    safe_ref = safe_ref[1:]
                module_path = f"{name}.{safe_ref}"
                self.logger.debug("Importing plugin module path: %s", module_path)
                module = importlib.import_module(module_path)
            else:
                # For local plugins, check plugin.py or __init__.py
                plugin_dir = self.plugins_dir / name
                if not plugin_dir.exists():
                    raise PluginNotFoundError(
                        f"Plugin directory not found: {plugin_dir}"
                    )

                if (plugin_dir / "plugin.py").exists():
                    self.logger.debug("Importing 'plugin.py' from: %s", plugin_dir)
                    module = importlib.import_module("plugin")
                elif (plugin_dir / "__init__.py").exists():
                    self.logger.debug("Importing '__init__.py' from: %s", plugin_dir)
                    module = importlib.import_module(name)
                else:
                    raise PluginNotFoundError(
                        f"Neither plugin.py nor __init__.py found in {plugin_dir}"
                    )

            # Search for a viable plugin class
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and attr.__module__ == module.__name__
                    and (
                        attr.__name__ in ["Plugin", "TestPlugin", "ExamplePlugin"]
                        or attr.__name__.lower() == name.lower()
                    )
                ):
                    plugin_class = attr
                    break

            if plugin_class is None:
                self.logger.error(
                    "No plugin class found in module '%s'.", module.__name__
                )
                raise PluginNotFoundError(
                    f"No plugin class found in module: {module.__name__}"
                )

            plugin_instance = plugin_class()
            self.logger.debug(
                "Registering plugin instance '%s' with the kernel...",
                plugin_class.__name__,
            )
            result = self.kernel.add_plugin(plugin_instance, plugin_name=name)
            self.logger.info("Plugin '%s' loaded and registered successfully!", name)
            return result

        except ImportError as e:
            self.logger.exception("Failed to import plugin '%s'.", name)
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

        Raises:
            Exception: If any plugin fails to install or load
        """
        self.logger.info("Installing and loading %d plugins...", len(plugin_configs))

        for config in plugin_configs:
            try:
                self.logger.debug(
                    "Processing plugin config: source=%s, version=%s, branch=%s",
                    config.source,
                    config.version,
                    config.branch,
                )
                self.install_plugin(config, base_dir)
                # Pass git_ref for GitHub plugins
                git_ref = config.git_ref if config.is_github_source else None
                self.load_plugin(config.name, git_ref)
            except Exception as e:
                # If a plugin fails, log it and raise immediately
                self.logger.exception(
                    "Error while installing/loading plugin '%s': %s",
                    config.name,
                    str(e),
                )
                raise

        self.logger.info("Finished installing/loading plugins.")
