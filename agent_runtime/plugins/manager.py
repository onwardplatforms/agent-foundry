# agent_runtime/plugins/manager.py
"""Plugin manager for handling SK plugin installation, loading, and lockfile checks with SHA-256."""

import hashlib
import importlib
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import requests
import click
from agent_runtime.cli.output import Style


class PluginNotFoundError(Exception):
    """Raised when a plugin cannot be found."""

    pass


class PluginConfig:
    """Configuration for a plugin."""

    def __init__(
        self,
        plugin_type: str,
        name: str,
        source: str,
        version: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
    ):
        """Initialize plugin configuration.

        Args:
            plugin_type: Type of plugin ("local" or "remote")
            name: Name of the plugin
            source: GitHub repository URL/shorthand or local path
            version: Git tag/commit (required for remote plugins)
            variables: Optional plugin-specific env variables
        """
        self.plugin_type = plugin_type
        self._name = name  # Store original name
        self.source = source
        self.variables = variables or {}

        # Validate based on plugin type
        if plugin_type == "local":
            if version:
                raise ValueError("Version cannot be specified for local plugins.")
            if not (source.startswith("./") or source.startswith("../")):
                raise ValueError("Local plugin paths must start with ./ or ../")
        elif plugin_type == "remote":
            if not version:
                raise ValueError("Version is required for remote plugins.")
        else:
            raise ValueError(f"Invalid plugin type: {plugin_type}")

        self.version = version

    @property
    def name(self) -> str:
        """Get the original unscoped name."""
        return self._name

    @property
    def scoped_name(self) -> str:
        """Get the scoped name (@local/name or @org/name)."""
        if self.plugin_type == "local":
            return f"@local/{self._name}"
        else:
            # For remote plugins, use the organization from the source
            parts = self._parse_github_source()
            return f"@{parts['org']}/{self._name}"

    def get_install_dir(
        self, plugins_dir: Path, base_dir: Optional[Path] = None
    ) -> Path:
        """Get standardized installation directory.

        Args:
            plugins_dir: Base directory for plugin installations (.plugins)
            base_dir: Base directory for resolving local plugin paths

        Returns:
            Path: Installation directory for the plugin
        """
        if self.plugin_type == "remote":
            parts = self._parse_github_source()
            version = self.version[1:] if self.version.startswith("v") else self.version
            return plugins_dir / parts["org"] / parts["plugin_name"] / version
        else:
            if not base_dir:
                raise ValueError("base_dir required for local plugins")
            return (base_dir / self.source).resolve()

    @property
    def is_github_source(self) -> bool:
        """Check if this is a remote GitHub plugin."""
        return self.plugin_type == "remote"

    @property
    def is_local_source(self) -> bool:
        """Check if this is a local plugin."""
        return self.plugin_type == "local"

    def _parse_github_source(self) -> Dict[str, str]:
        """Parse GitHub URL or shorthand into components."""
        if not self.is_github_source:
            raise ValueError("Cannot parse GitHub source for local plugin")

        # Handle full GitHub URLs
        if self.source.startswith(("https://github.com/", "github.com/")):
            url = self.source.replace("https://github.com/", "").replace(
                "github.com/", ""
            )
            parts = url.rstrip("/").split("/")
            if len(parts) < 2:
                raise ValueError(f"Invalid GitHub URL: {self.source}")
            org = parts[0]
            plugin_name = parts[1]
        else:
            # Handle org/plugin shorthand
            parts = self.source.split("/")
            if len(parts) != 2:
                raise ValueError(f"Invalid plugin shorthand: {self.source}")
            org = parts[0]
            plugin_name = parts[1]

        # Construct the actual repository name with the agentruntime-plugin prefix
        repo = f"agentruntime-plugin-{plugin_name}"

        return {
            "org": org,
            "repo": repo,
            "plugin_name": plugin_name,
            "clone_url": f"https://github.com/{org}/{repo}",
        }

    def get_github_commit_sha(self) -> Optional[str]:
        """Get the commit SHA for a GitHub tag using the GitHub API."""
        if not self.is_github_source:
            return None

        parts = self._parse_github_source()
        org = parts["org"]
        repo = parts["repo"]

        # Try with and without v prefix
        refs_to_try = []
        if self.version.startswith("v"):
            refs_to_try.append(self.version)
            refs_to_try.append(self.version[1:])
        else:
            refs_to_try.append(f"v{self.version}")
            refs_to_try.append(self.version)

        for ref in refs_to_try:
            url = f"https://api.github.com/repos/{org}/{repo}/git/refs/tags/{ref}"
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    data = response.json()
                    return data["object"]["sha"]
            except Exception as e:
                logging.getLogger(__name__).warning(
                    "Failed to get commit SHA for %s/%s@%s: %s", org, repo, ref, e
                )
                continue

        return None

    @property
    def git_ref(self) -> str:
        """Return the git ref for GitHub sources (version)."""
        if not self.is_github_source:
            raise ValueError("git_ref valid only for GitHub sources.")
        return self.version

    @property
    def install_path(self) -> str:
        """Get the installation path for the plugin."""
        if self.is_github_source:
            parts = self._parse_github_source()
            return f"{parts['org']}/{parts['plugin_name']}"
        else:
            return self.source


class PluginManager:
    """Manager for SK plugins with lockfile and SHA-256 support."""

    PLUGINS_DIR = ".plugins"

    def __init__(self, base_dir: Path, kernel: Any = None) -> None:
        self.base_dir = base_dir
        self.plugins_dir = base_dir / ".plugins"
        self.kernel = kernel
        self.logger = logging.getLogger(__name__)
        self.plugin_configs: Dict[str, PluginConfig] = {}

        # Create plugins directory if it doesn't exist
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        # Add plugins dir to Python path
        plugins_path = str(self.plugins_dir.resolve())
        if plugins_path not in sys.path:
            sys.path.append(plugins_path)
            self.logger.debug("Added plugins dir to sys.path: %s", plugins_path)

    def _set_plugin_vars(self, cfg: PluginConfig) -> None:
        """Set plugin variables in env with AGENT_VAR_ prefix."""
        for k, v in cfg.variables.items():
            # Handle environment variable references ($ENV_VAR)
            if isinstance(v, str):
                if v.startswith("$"):
                    # Handle environment variable references ($ENV_VAR)
                    env_name = v[1:]
                    resolved = os.getenv(env_name, "")
                    if not resolved:
                        self.logger.warning(
                            "Env var '%s' not found for plugin var '%s'.", env_name, k
                        )
                    key = f"AGENT_VAR_{k.upper()}"
                    os.environ[key] = resolved
                else:
                    os.environ[f"AGENT_VAR_{k.upper()}"] = v
            else:
                # Non-string value
                key = f"AGENT_VAR_{k.upper()}"
                if v is None:
                    v = ""
                os.environ[key] = str(v)
                self.logger.debug("Set %s=%s (plugin '%s')", key, v, cfg.name)

    def _clone_github_plugin(self, cfg: PluginConfig) -> None:
        """Clone a plugin from GitHub."""
        parts = cfg._parse_github_source()
        version_dir = cfg.get_install_dir(self.plugins_dir)

        # Create parent directories if they don't exist
        version_dir.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing version directory if it exists
        if version_dir.exists():
            shutil.rmtree(version_dir)

        self.logger.debug(
            "Cloning plugin '%s' from '%s' at version '%s'",
            cfg.name,
            parts["clone_url"],
            cfg.version,
        )

        try:
            # First clone the repository
            subprocess.run(
                ["git", "clone", parts["clone_url"], str(version_dir)],
                check=True,
                capture_output=True,
                text=True,
            )

            # Fetch tags
            subprocess.run(
                ["git", "fetch", "--tags"],
                cwd=version_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            # Try checking out the tag/version
            ref = cfg.git_ref
            if not ref.startswith("v"):
                possible_ref = f"v{ref}"
            else:
                possible_ref = ref

            try:
                subprocess.run(
                    ["git", "checkout", possible_ref],
                    cwd=version_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError:
                # If that fails, try the plain ref
                if possible_ref.startswith("v"):
                    subprocess.run(
                        ["git", "checkout", ref],
                        cwd=version_dir,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                else:
                    raise

            # Clean up .git directory
            git_dir = version_dir / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)

            self.logger.debug("Plugin '%s' cloned successfully.", cfg.name)
        except subprocess.CalledProcessError as e:
            # Clean up the failed clone
            if version_dir.exists():
                shutil.rmtree(version_dir)
            raise RuntimeError(f"Failed to clone plugin: {e.stderr}") from e

    def install_plugin(
        self, cfg: PluginConfig, force_reinstall: bool = False, quiet: bool = False
    ) -> None:
        """Install a single plugin (download/copy) if needed."""
        self.logger.debug(
            "Processing plugin '%s' from '%s'. (force=%s)",
            cfg.name,
            cfg.source,
            force_reinstall,
        )

        if cfg.is_github_source:
            version_dir = cfg.get_install_dir(self.plugins_dir)

            # Only check commit SHA if not forcing reinstall
            if not force_reinstall and version_dir.exists():
                # Get current commit SHA from GitHub API
                current_sha = cfg.get_github_commit_sha()
                if current_sha:
                    self.logger.debug(
                        "Current SHA for plugin '%s': %s", cfg.name, current_sha
                    )

                    lock_data = self.read_lockfile(self.base_dir / "plugins.lock.json")
                    for plugin in lock_data.get("plugins", []):
                        if plugin["name"] == cfg.name:
                            locked_sha = plugin.get("commit_sha")
                            self.logger.debug(
                                "Locked SHA for plugin '%s': %s", cfg.name, locked_sha
                            )

                            if (
                                locked_sha == current_sha
                                and plugin.get("version") == cfg.version
                            ):
                                if not quiet:
                                    click.echo(
                                        Style.plugin_status(cfg.name, "up to date")
                                    )
                                self._set_plugin_vars(cfg)
                                return
                            else:
                                if not quiet:
                                    click.echo(
                                        Style.plugin_status(
                                            cfg.name, "updating", "yellow"
                                        )
                                    )
                                break

            # If we get here, we need to clone/re-clone
            self._clone_github_plugin(cfg)
            base_path = str(version_dir.parent)
            if base_path not in sys.path:
                sys.path.append(base_path)
                self.logger.debug("Added plugin directory to sys.path: %s", base_path)
        else:
            # For local plugins, just verify the source exists and set variables
            src_path = cfg.get_install_dir(self.plugins_dir, self.base_dir)
            if not src_path.exists():
                raise FileNotFoundError(f"Local plugin source not found: {src_path}")

            # Check if we need to reinstall by comparing SHA
            if not force_reinstall:
                current_sha = self._compute_directory_sha(src_path)
                self.logger.debug(
                    "Current SHA for local plugin '%s': %s", cfg.name, current_sha
                )

                lock_data = self.read_lockfile(self.base_dir / "plugins.lock.json")
                for plugin in lock_data.get("plugins", []):
                    if plugin["name"] == cfg.name:
                        locked_sha = plugin.get("sha")
                        self.logger.debug(
                            "Locked SHA for local plugin '%s': %s", cfg.name, locked_sha
                        )

                        if locked_sha == current_sha:
                            if not quiet:
                                click.echo(Style.plugin_status(cfg.name, "up to date"))
                            self._set_plugin_vars(cfg)
                            return
                        else:
                            if not quiet:
                                click.echo(
                                    Style.plugin_status(cfg.name, "updating", "yellow")
                                )

            # Add source directory's parent to sys.path if not already there
            parent_dir = str(src_path.parent.resolve())
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
                self.logger.debug("Added parent directory to sys.path: %s", parent_dir)

        self._set_plugin_vars(cfg)
        self.logger.debug("Plugin '%s' processed successfully.", cfg.name)

    def load_plugin(self, name: str, git_ref: Optional[str] = None) -> Any:
        """Load a plugin from .plugins or local source."""
        self.logger.debug("Loading plugin '%s' (ref=%s).", name, git_ref or "local")

        if name not in self.plugin_configs:
            raise PluginNotFoundError(f"No configuration found for plugin: {name}")

        plugin_config = self.plugin_configs[name]

        # Set plugin variables before loading the module
        self._set_plugin_vars(plugin_config)

        if plugin_config.is_github_source:
            parts = plugin_config._parse_github_source()
            version = git_ref if git_ref else plugin_config.version
            if version.startswith("v"):
                version = version[1:]
            version_dir = (
                self.plugins_dir / parts["org"] / parts["plugin_name"] / version
            )

            self.logger.debug("Looking for plugin in directory: %s", version_dir)
            if not version_dir.exists():
                self.logger.error("Plugin version directory not found: %s", version_dir)
                raise PluginNotFoundError(
                    f"Plugin version directory not found: {version_dir}"
                )

            version_dir_str = str(version_dir.resolve())
            if version_dir_str not in sys.path:
                sys.path.insert(0, version_dir_str)
                self.logger.debug(
                    "Added version directory to sys.path: %s", version_dir_str
                )

            try:
                module = importlib.import_module("__init__")
            except ImportError as e:
                self.logger.error("Failed to import plugin module: %s", e)
                raise PluginNotFoundError(f"Failed to import plugin module: {e}")
        else:
            plugin_path = plugin_config.get_install_dir(self.plugins_dir, self.base_dir)
            if not plugin_path.exists():
                raise PluginNotFoundError(
                    f"Local plugin source not found: {plugin_path}"
                )

            plugin_dir = str(plugin_path.parent)
            if plugin_dir not in sys.path:
                sys.path.insert(0, plugin_dir)
                self.logger.debug("Added plugin directory to sys.path: %s", plugin_dir)

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

        # Find any class that has kernel functions
        plugin_class = None
        self.logger.debug("Searching for plugin classes in module: %s", module.__name__)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            self.logger.debug(
                "Checking attribute: %s (type: %s)", attr_name, type(attr)
            )

            if not isinstance(attr, type):
                continue

            if attr.__module__ != module.__name__:
                self.logger.debug(
                    "Skipping %s: wrong module (%s != %s)",
                    attr_name,
                    attr.__module__,
                    module.__name__,
                )
                continue

            # Check for kernel functions in the class
            has_kernel_functions = False
            self.logger.debug("Checking methods of class: %s", attr_name)

            for method_name, method in attr.__dict__.items():
                if method_name.startswith("__"):
                    continue

                try:
                    self.logger.debug(
                        "Checking method: %s (callable: %s, kernel_function: %s)",
                        method_name,
                        callable(method),
                        (
                            hasattr(method, "__kernel_function__")
                            if callable(method)
                            else False
                        ),
                    )

                    if callable(method) and hasattr(method, "__kernel_function__"):
                        self.logger.debug(f"Found kernel function: {method_name}")
                        has_kernel_functions = True
                        break
                except Exception as e:
                    self.logger.debug(f"Error checking method {method_name}: {e}")
                    continue

            if has_kernel_functions:
                plugin_class = attr
                self.logger.debug(
                    "Found plugin class: %s with kernel functions", attr.__name__
                )
                break

        if not plugin_class:
            self.logger.error(
                "No plugin class with kernel functions found in module: %s",
                module.__name__,
            )
            raise PluginNotFoundError(
                f"No plugin class with kernel functions found in module: {module.__name__}"
            )

        self.logger.debug("Instantiating plugin class: %s", plugin_class.__name__)
        instance = plugin_class()

        # Register with kernel using sanitized scoped name to prevent collisions
        sanitized_name = (
            plugin_config.scoped_name.replace("/", "_")
            .replace("@", "")
            .replace("-", "_")
        )
        self.logger.debug(
            "Registering plugin with kernel as: %s (from %s)",
            sanitized_name,
            plugin_config.scoped_name,
        )
        return self.kernel.add_plugin(instance, plugin_name=sanitized_name)

    def compare_with_lock(
        self, plugins: List[PluginConfig], lock_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Compare current plugins with the global lockfile and return detailed changes."""
        changes = {"added": [], "removed": [], "updated": []}

        if lock_data is None:
            lock_path = self.base_dir / "plugins.lock.json"
            if not lock_path.exists():
                self.logger.debug("No lockfile found at %s", lock_path)
                # Mark all plugins as added
                changes["added"] = [{"name": p.scoped_name} for p in plugins]
                return changes
            lock_data = self.read_lockfile(lock_path)

        self.logger.debug("Comparing plugins with lock data: %s", lock_data)
        current_scoped_names = set(p.scoped_name for p in plugins)
        self.logger.debug("Current plugins: %s", current_scoped_names)

        locked_map = {p["scoped_name"]: p for p in lock_data.get("plugins", [])}
        locked_scoped_names = set(locked_map.keys())
        self.logger.debug("Locked plugins: %s", list(locked_scoped_names))

        # Check for added plugins
        added_plugins = current_scoped_names - locked_scoped_names
        changes["added"].extend([{"name": name} for name in added_plugins])

        # Check for removed plugins
        removed_plugins = locked_scoped_names - current_scoped_names
        changes["removed"].extend([{"name": name} for name in removed_plugins])

        # Check for updated plugins
        for cfg in plugins:
            if cfg.scoped_name not in locked_map:
                continue

            locked = locked_map[cfg.scoped_name]
            update_info = {"name": cfg.scoped_name, "changes": []}

            if cfg.is_github_source:
                if cfg.version != locked.get("version"):
                    update_info["changes"].append(
                        {
                            "type": "version",
                            "old": locked.get("version"),
                            "new": cfg.version,
                        }
                    )

                current_sha = cfg.get_github_commit_sha()
                if current_sha and current_sha != locked.get("commit_sha"):
                    update_info["changes"].append(
                        {
                            "type": "commit",
                            "old": locked.get("commit_sha"),
                            "new": current_sha,
                        }
                    )
            else:
                src_path = cfg.get_install_dir(self.plugins_dir, self.base_dir)
                if src_path.exists():
                    current_sha = self._compute_directory_sha(src_path)
                    locked_sha = locked.get("sha")
                    if current_sha != locked_sha:
                        update_info["changes"].append(
                            {"type": "sha", "old": locked_sha, "new": current_sha}
                        )

            if update_info["changes"]:
                changes["updated"].append(update_info)

        return changes

    def install_and_load_plugins(
        self, configs: List[PluginConfig], force_reinstall: bool = False
    ) -> None:
        """Install and load multiple plugins."""
        self.logger.debug(
            "Installing/loading %d plugins (force=%s)...", len(configs), force_reinstall
        )

        # Clear existing configs and store new ones using scoped names
        self.plugin_configs.clear()
        for cfg in configs:
            self.plugin_configs[cfg.scoped_name] = cfg

        if not force_reinstall:
            changes = self.compare_with_lock(configs)
            if not any(changes.values()):  # No changes detected
                self.logger.debug("All plugins are up to date.")
                # Still need to load them
                for cfg in configs:
                    self.load_plugin(
                        cfg.scoped_name, cfg.version if cfg.is_github_source else None
                    )
                click.echo(Style.header("Initializing agent configuration..."))
                click.echo("")
                click.echo(Style.success("All plugins are up to date"))
                click.echo(Style.success("All plugins loaded from local cache"))
                click.echo(
                    Style.success(
                        "Agent configuration has been successfully initialized"
                    )
                )
                click.echo("")
                click.echo(
                    "You may now begin working with your agent. All commands should work."
                )
                click.echo(
                    "\nIf you ever change plugins or their configuration, rerun the init"
                )
                click.echo(
                    "command to reinitialize your working directory. If you forget, other"
                )
                click.echo(
                    "commands will detect it and remind you to do so if necessary."
                )
                return

            # Track plugins we've already reported on to avoid duplicates
            reported_plugins = set()

            # Separate configs by type
            local_configs = [c for c in configs if c.is_local_source]
            remote_configs = [c for c in configs if c.is_github_source]

            # Display initialization header
            click.echo(Style.header("Initializing agent configuration..."))
            click.echo("")

            # Display local plugins section if there are any local plugins
            if local_configs:
                click.echo("- Local plugins:")

                # Process all local plugins
                for cfg in local_configs:
                    if cfg.scoped_name in reported_plugins:
                        continue
                    reported_plugins.add(cfg.scoped_name)

                    # Check if this plugin has updates
                    update_info = next(
                        (p for p in changes["updated"] if p["name"] == cfg.scoped_name),
                        None,
                    )

                    if update_info:
                        changes_desc = []
                        for change in update_info["changes"]:
                            if change["type"] == "sha":
                                changes_desc.append("local changes detected")
                        click.echo(
                            Style.plugin_status(
                                cfg.scoped_name,
                                f"updating ({', '.join(changes_desc)})",
                                "yellow",
                            )
                        )
                    else:
                        click.echo(Style.plugin_status(cfg.scoped_name, "up to date"))

            # Display remote plugins section if there are any remote plugins
            if remote_configs:
                if local_configs:  # Add a newline if we had local plugins
                    click.echo("")
                click.echo("- Remote plugins:")

                # Process all remote plugins
                for cfg in remote_configs:
                    if cfg.scoped_name in reported_plugins:
                        continue
                    reported_plugins.add(cfg.scoped_name)

                    # Check if this plugin has updates
                    update_info = next(
                        (p for p in changes["updated"] if p["name"] == cfg.scoped_name),
                        None,
                    )

                    if update_info:
                        changes_desc = []
                        for change in update_info["changes"]:
                            if change["type"] == "version":
                                changes_desc.append(
                                    f"version {change['old']} → {change['new']}"
                                )
                            elif change["type"] == "commit":
                                old_commit = (
                                    change["old"][:7] if change["old"] else "none"
                                )
                                new_commit = (
                                    change["new"][:7] if change["new"] else "none"
                                )
                                changes_desc.append(
                                    f"commit {old_commit} → {new_commit}"
                                )
                        click.echo(
                            Style.plugin_status(
                                cfg.scoped_name,
                                f"updating ({', '.join(changes_desc)})",
                                "yellow",
                            )
                        )
                    else:
                        click.echo(Style.plugin_status(cfg.scoped_name, "up to date"))

            # Display any new plugins that weren't covered above
            if changes["added"]:
                if (
                    local_configs or remote_configs
                ):  # Add a newline if we had other sections
                    click.echo("")
                click.echo("- Installing new plugins:")
                for plugin in changes["added"]:
                    if plugin["name"] in reported_plugins:
                        continue
                    reported_plugins.add(plugin["name"])
                    click.echo(
                        Style.plugin_status(plugin["name"], "installing", "blue")
                    )

            # Display any removed plugins
            if changes["removed"]:
                if (
                    local_configs or remote_configs or changes["added"]
                ):  # Add a newline if we had other sections
                    click.echo("")
                click.echo("- Removing plugins:")
                for plugin in changes["removed"]:
                    if plugin["name"] in reported_plugins:
                        continue
                    reported_plugins.add(plugin["name"])
                    click.echo(Style.plugin_status(plugin["name"], "removing", "red"))

        # Install plugins
        local_configs = [c for c in configs if c.is_local_source]
        remote_configs = [c for c in configs if c.is_github_source]

        if local_configs:
            for cfg in local_configs:
                self.install_plugin(cfg, force_reinstall, quiet=True)

        if remote_configs:
            for cfg in remote_configs:
                self.install_plugin(cfg, force_reinstall, quiet=True)

        # Load them all
        for cfg in configs:
            self.load_plugin(
                cfg.scoped_name, cfg.version if cfg.is_github_source else None
            )

        # Update lockfile
        new_data = self.create_lock_data()
        self.write_lockfile(self.base_dir / "plugins.lock.json", new_data)
        self.logger.debug("Lockfile updated: %s", "plugins.lock.json")

        # Final success message
        click.echo("")
        click.echo(
            Style.success("Agent configuration has been successfully initialized")
        )
        click.echo("")
        click.echo(
            "You may now begin working with your agent. All commands should work."
        )
        click.echo(
            "\nIf you ever change plugins or their configuration, rerun the init"
        )
        click.echo(
            "command to reinitialize your working directory. If you forget, other"
        )
        click.echo("commands will detect it and remind you to do so if necessary.")

    def create_lock_data(self) -> Dict[str, Any]:
        """Create lock data for all installed plugins."""
        plugins_data = []

        # Only include plugins that are in the current configuration
        for scoped_name, cfg in self.plugin_configs.items():
            plugin_data = {
                "name": cfg.name,
                "scoped_name": scoped_name,
                "source": cfg.source,
                "type": "remote" if cfg.is_github_source else "local",
            }

            if cfg.is_github_source:
                plugin_data.update(
                    {"version": cfg.version, "commit_sha": cfg.get_github_commit_sha()}
                )
            else:
                src_path = (self.base_dir / cfg.source).resolve()
                if src_path.exists():
                    plugin_data["sha"] = self._compute_directory_sha(src_path)
                else:
                    self.logger.warning(
                        "Local plugin path does not exist: %s", src_path
                    )

            plugins_data.append(plugin_data)

        return {"plugins": plugins_data}

    def _compute_directory_sha(self, directory: Path) -> str:
        """Compute SHA256 hash of a directory's contents."""
        sha256_hash = hashlib.sha256()
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for file in sorted(files):
                if file.endswith((".py", ".txt", ".md", ".json", ".yaml", ".yml")):
                    file_path = Path(root) / file
                    try:
                        with file_path.open("rb") as f:
                            rel_path = file_path.relative_to(directory)
                            sha256_hash.update(str(rel_path).encode())
                            for chunk in iter(lambda: f.read(4096), b""):
                                sha256_hash.update(chunk)
                    except (IOError, OSError) as e:
                        self.logger.warning("Failed to read file %s: %s", file_path, e)
                        continue

        return sha256_hash.hexdigest()

    def read_lockfile(self, path: Path) -> Dict[str, Any]:
        """Read existing lockfile if present."""
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                return cast(Dict[str, Any], json.load(f))
        except (OSError, json.JSONDecodeError):
            self.logger.warning("Unable to read lockfile.")
            return {}

    def write_lockfile(self, path: Path, data: Dict[str, Any]) -> None:
        """Write updated lock data to lockfile."""
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.logger.debug("Lockfile updated: %s", path)

    def get_openai_functions(self) -> Dict[str, Any]:
        """Convert registered plugins to OpenAI function definitions."""
        if not self.kernel:
            return {"functions": [], "function_call": "auto"}

        functions = []
        for plugin in self.kernel.plugins.values():
            for func in plugin.functions.values():
                # Convert each function to OpenAI format
                function_def = {
                    "name": f"{plugin.name}_{func.name}",
                    "description": func.description,
                    "parameters": {"type": "object", "properties": {}, "required": []},
                }

                # Add parameters
                for param in func.parameters:
                    function_def["parameters"]["properties"][param.name] = {
                        "type": "string",  # Default to string for simplicity
                        "description": param.description or "",
                    }
                    # Check if parameter is required based on default value
                    if param.default_value is None and param.type_ != "bool":
                        function_def["parameters"]["required"].append(param.name)

                functions.append(function_def)

        return {"functions": functions, "function_call": "auto"}
