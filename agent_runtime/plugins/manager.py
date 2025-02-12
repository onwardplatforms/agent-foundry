# agent_runtime/plugins/manager.py
"""Plugin manager for handling SK plugin installation, loading, and lockfile checks with SHA-256."""

import hashlib
import importlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import requests
from semantic_kernel import Kernel
import click
from agent_runtime.cli.output import Style


# ANSI color codes for terminal output
class Colors:
    """Terminal color codes."""

    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[36m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def cli_message(msg: str, color: str = "", bold: bool = False) -> None:
    """Print a CLI message with optional color and formatting."""
    if os.getenv("NO_COLOR"):  # Respect NO_COLOR env var
        print(msg)
    else:
        bold_code = Colors.BOLD if bold else ""
        print(f"{bold_code}{color}{msg}{Colors.RESET}")


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
            if v.startswith("$"):
                env_name = v[1:]
                resolved = os.getenv(env_name, "")
                if not resolved:
                    self.logger.warning(
                        "Env var '%s' not found for plugin var '%s'.", env_name, k
                    )
                v = resolved
            key = f"AGENT_VAR_{k.upper()}"
            os.environ[key] = v
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

    def install_plugin(self, cfg: PluginConfig, force_reinstall: bool = False) -> None:
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
                                click.echo(Style.plugin_status(cfg.name, "up to date"))
                                self._set_plugin_vars(cfg)
                                return
                            else:
                                click.echo(
                                    Style.plugin_status(cfg.name, "updating", "yellow")
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
                            click.echo(Style.plugin_status(cfg.name, "up to date"))
                            self._set_plugin_vars(cfg)
                            return
                        else:
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
        """Load a plugin from .plugins or local source.

        Args:
            name: Name of the plugin's scoped_name (e.g. @local/echo)
            git_ref: Optional git reference (version) for GitHub plugins

        Returns:
            The loaded plugin instance

        Raises:
            PluginNotFoundError: If plugin cannot be found
            ImportError: If plugin cannot be imported
        """
        self.logger.debug("Loading plugin '%s' (ref=%s).", name, git_ref or "local")

        if name not in self.plugin_configs:
            raise PluginNotFoundError(f"No configuration found for plugin: {name}")

        plugin_config = self.plugin_configs[name]

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
            self.logger.error("No plugin class found in module: %s", module.__name__)
            raise PluginNotFoundError(f"No plugin class in module: {module.__name__}")

        self.logger.debug("Instantiating plugin class: %s", plugin_class.__name__)
        instance = plugin_class()

        # Register with kernel using the plugin's 'name'
        self.logger.debug("Registering plugin with kernel as: %s", plugin_config.name)
        return self.kernel.add_plugin(instance, plugin_name=plugin_config.name)

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

        if not force_reinstall and self.compare_with_lock(configs):
            self.logger.debug("All plugins are up to date.")
            # Still need to load them
            for cfg in configs:
                self.load_plugin(
                    cfg.scoped_name, cfg.version if cfg.is_github_source else None
                )
            click.echo(Style.success("All plugins are up to date"))
            return

        click.echo(Style.header("\nInitializing plugins..."))

        # Separate local/remote
        local_configs = [c for c in configs if c.is_local_source]
        remote_configs = [c for c in configs if c.is_github_source]

        if local_configs:
            click.echo(Style.info("\nLocal plugins:"))
            for cfg in local_configs:
                self.install_plugin(cfg, force_reinstall)

        if remote_configs:
            click.echo(Style.info("\nRemote plugins:"))
            for cfg in remote_configs:
                self.install_plugin(cfg, force_reinstall)

        # Load them all
        for cfg in configs:
            self.load_plugin(
                cfg.scoped_name, cfg.version if cfg.is_github_source else None
            )

        # Update lockfile
        new_data = self.create_lock_data()
        self.write_lockfile(self.base_dir / "plugins.lock.json", new_data)
        self.logger.debug("Lockfile updated: %s", "plugins.lock.json")
        click.echo(Style.success("\nInitialization complete"))

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

    def compare_with_lock(
        self, plugins: List[PluginConfig], lock_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Compare current plugins with the global lockfile."""
        if lock_data is None:
            lock_path = self.base_dir / "plugins.lock.json"
            if not lock_path.exists():
                self.logger.debug("No lockfile found at %s", lock_path)
                return False
            lock_data = self.read_lockfile(lock_path)

        self.logger.debug("Comparing plugins with lock data: %s", lock_data)
        current_scoped_names = set(p.scoped_name for p in plugins)
        self.logger.debug("Current plugins: %s", current_scoped_names)

        locked_map = {p["scoped_name"]: p for p in lock_data.get("plugins", [])}
        locked_scoped_names = set(locked_map.keys())
        self.logger.debug("Locked plugins: %s", list(locked_scoped_names))

        # Check for plugins that have been removed from configuration
        removed_plugins = locked_scoped_names - current_scoped_names
        if removed_plugins:
            self.logger.debug("Plugins have been removed: %s", removed_plugins)
            return False

        # Check for plugins that have been added to configuration
        added_plugins = current_scoped_names - locked_scoped_names
        if added_plugins:
            self.logger.debug("New plugins need to be added: %s", added_plugins)
            return False

        # For each plugin, check source and type
        for cfg in plugins:
            locked = locked_map[cfg.scoped_name]

            # Compare source and type
            if cfg.source != locked["source"]:
                self.logger.debug(
                    "Source mismatch for '%s': current=%s, locked=%s",
                    cfg.scoped_name,
                    cfg.source,
                    locked["source"],
                )
                return False

            if (cfg.is_github_source and locked["type"] != "remote") or (
                not cfg.is_github_source and locked["type"] != "local"
            ):
                self.logger.debug(
                    "Type mismatch for '%s': expected=%s, got=%s",
                    cfg.scoped_name,
                    "remote" if cfg.is_github_source else "local",
                    locked["type"],
                )
                return False

            if cfg.is_github_source:
                if cfg.version != locked.get("version"):
                    self.logger.debug(
                        "Version mismatch for '%s': current=%s, locked=%s",
                        cfg.scoped_name,
                        cfg.version,
                        locked.get("version"),
                    )
                    return False

                current_sha = cfg.get_github_commit_sha()
                if not current_sha:
                    self.logger.debug(
                        "Could not get commit SHA for '%s'", cfg.scoped_name
                    )
                    return False

                if current_sha != locked.get("commit_sha"):
                    self.logger.debug(
                        "Commit SHA mismatch for '%s': current=%s, locked=%s",
                        cfg.scoped_name,
                        current_sha,
                        locked.get("commit_sha"),
                    )
                    return False
            else:
                src_path = cfg.get_install_dir(self.plugins_dir, self.base_dir)
                if not src_path.exists():
                    self.logger.debug("Local plugin path does not exist: %s", src_path)
                    return False

                current_sha = self._compute_directory_sha(src_path)
                locked_sha = locked.get("sha")
                if current_sha != locked_sha:
                    self.logger.debug(
                        "SHA mismatch for '%s': current=%s, locked=%s",
                        cfg.scoped_name,
                        current_sha,
                        locked_sha,
                    )
                    return False

        return True

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
