from typing import Dict, Any, Optional
import sys
import importlib


class PluginManager:
    def _has_plugins_changed(self, lock_data: Dict[str, Any]) -> bool:
        """Check if the plugin configuration has changed since last init."""
        self.logger.debug(f"Comparing plugins with lock data: {lock_data}")

        # Get list of current plugin scoped names
        current_plugins = [
            cfg_item.scoped_name for cfg_item in self.plugin_configs.values()
        ]
        self.logger.debug(f"Current plugins: {current_plugins}")

        # Create map of locked plugins by scoped name
        locked_plugins = {
            plugin["scoped_name"]: plugin for plugin in lock_data.get("plugins", [])
        }
        self.logger.debug(f"Locked plugins: {locked_plugins}")

        # Check if any required plugins are missing from the lockfile
        for plugin_name in current_plugins:
            if plugin_name not in locked_plugins:
                self.logger.debug(
                    f"Required plugin {plugin_name} not found in lockfile"
                )
                return True

        # Check if any plugins in the lockfile match our current configuration
        for plugin_name in current_plugins:
            cfg_item = self.plugin_configs[plugin_name]
            locked = locked_plugins[plugin_name]

            # Compare source and type
            if cfg_item.source != locked["source"]:
                self.logger.debug(
                    f"Source mismatch for '{plugin_name}': current={cfg_item.source}, locked={locked['source']}"
                )
                return True

            if (cfg_item.is_github_source and locked["type"] != "remote") or (
                not cfg_item.is_github_source and locked["type"] != "local"
            ):
                self.logger.debug(
                    f"Type mismatch for '{plugin_name}': expected={cfg_item.plugin_type}, got={locked['type']}"
                )
                return True

            # For remote plugins, check version
            if cfg_item.is_github_source:
                if cfg_item.version != locked["version"]:
                    self.logger.debug(
                        f"Version mismatch for '{plugin_name}': current={cfg_item.version}, locked={locked['version']}"
                    )
                    return True

        return False

    def load_plugin(self, name: str, git_ref: Optional[str] = None) -> Any:
        """Load a plugin from .plugins or local source.

        Args:
            name: Name of the plugin to load
            git_ref: Optional git reference (version) for GitHub plugins

        Returns:
            The loaded plugin instance

        Raises:
            PluginNotFoundError: If plugin cannot be found
            ImportError: If plugin cannot be imported
        """
        self.logger.debug("Loading plugin '%s' (ref=%s).", name, git_ref or "local")

        try:
            # Get the plugin config
            if name not in self.plugin_configs:
                raise PluginNotFoundError(f"No configuration found for plugin: {name}")

            plugin_config = self.plugin_configs[name]

            if plugin_config.is_github_source:  # Remote plugin
                parts = plugin_config._parse_github_source()

                # Construct the path: .plugins/<org>/<plugin_name>/<version>
                version = git_ref
                if version is None:
                    version = plugin_config.version
                if version.startswith("v"):
                    version = version[1:]
                version_dir = (
                    self.plugins_dir / parts["org"] / parts["plugin_name"] / version
                )

                self.logger.debug("Looking for plugin in directory: %s", version_dir)

                if not version_dir.exists():
                    self.logger.error(
                        "Plugin version directory not found: %s", version_dir
                    )
                    raise PluginNotFoundError(
                        f"Plugin version directory not found: {version_dir}"
                    )

                # Add the version directory to sys.path if not already there
                version_dir_str = str(version_dir.resolve())
                if version_dir_str not in sys.path:
                    sys.path.insert(0, version_dir_str)
                    self.logger.debug(
                        "Added version directory to sys.path: %s", version_dir_str
                    )

                # Import the module directly from the version directory
                try:
                    module = importlib.import_module("__init__")
                except ImportError as e:
                    self.logger.error("Failed to import plugin module: %s", e)
                    raise PluginNotFoundError(f"Failed to import plugin module: {e}")
            else:  # Local plugin
                # For local plugins, look in the original source directory
                plugin_path = (self.base_dir / plugin_config.source).resolve()

                if not plugin_path.exists():
                    raise PluginNotFoundError(
                        f"Local plugin source not found: {plugin_path}"
                    )

                # Add plugin directory to sys.path if not already there
                plugin_dir = str(plugin_path.parent)
                if plugin_dir not in sys.path:
                    sys.path.insert(0, plugin_dir)
                    self.logger.debug(
                        "Added plugin directory to sys.path: %s", plugin_dir
                    )

                try:
                    self.logger.debug(
                        "Attempting to import local plugin: %s", plugin_config.name
                    )
                    module = importlib.import_module(f"{plugin_path.name}")
                except ImportError as e:
                    self.logger.error(
                        "Failed to import local plugin '%s': %s", plugin_config.name, e
                    )
                    raise PluginNotFoundError(
                        f"Failed to import local plugin {plugin_config.name}: {e}"
                    )

            self.logger.debug("Looking for plugin class in module: %s", module.__name__)
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and attr.__module__ == module.__name__
                    and (
                        attr.__name__ in ["Plugin", "TestPlugin", "ExamplePlugin"]
                        or attr.__name__.lower() == plugin_config.name.lower()
                    )
                ):
                    plugin_class = attr
                    self.logger.debug("Found plugin class: %s", attr.__name__)
                    break

            if not plugin_class:
                self.logger.error(
                    "No plugin class found in module: %s", module.__name__
                )
                raise PluginNotFoundError(
                    f"No plugin class in module: {module.__name__}"
                )

            self.logger.debug("Instantiating plugin class: %s", plugin_class.__name__)
            instance = plugin_class()

            # Use the scoped name when registering with kernel
            self.logger.debug(
                "Registering plugin with kernel as: %s", plugin_config.scoped_name
            )
            return self.kernel.add_plugin(
                instance, plugin_name=plugin_config.scoped_name
            )

        except ImportError as e:
            self.logger.exception("Import failed for plugin '%s'.", name)
            raise PluginNotFoundError(f"Failed to import plugin {name}: {e}") from e
