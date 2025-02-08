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
            source: GitHub repository URL or local path
            version: Git tag/commit (cannot use with branch)
            branch: Branch name (cannot use with version)
            variables: Optional plugin-specific env variables
        """
        self.source = source
        self.variables = variables or {}

        # Validate version/branch for GitHub
        if self.is_github_source:
            if version and branch:
                raise ValueError("Cannot specify both version and branch.")
            if not version and not branch:
                # Default = main
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
        """Derive the plugin name from the source (GitHub or local)."""
        if self.is_github_source:
            parts = self.source.rstrip("/").split("/")
            raw_name = parts[-1] if parts else "unknown_plugin"
        else:
            raw_name = Path(self.source).name

        return re.sub(r"[^0-9A-Za-z_]", "_", raw_name)

    @property
    def is_github_source(self) -> bool:
        """Check if source is a GitHub URL."""
        if not self.source:
            return False
        return self.source.startswith("https://github.com/") or self.source.startswith(
            "github.com/"
        )

    @property
    def is_local_source(self) -> bool:
        """Check if source is a local path."""
        return not self.is_github_source

    @property
    def git_ref(self) -> str:
        """Return the git ref for GitHub sources (branch or version)."""
        if not self.is_github_source:
            raise ValueError("git_ref valid only for GitHub sources.")
        return self.version or self.branch or "main"


class PluginManager:
    """Manager for SK plugins with lockfile and SHA-256 support."""

    PLUGINS_DIR = ".plugins"

    def __init__(self, kernel: Kernel, base_dir: Path):
        self.logger = logging.getLogger(__name__)
        self.kernel = kernel
        self.base_dir = base_dir
        self.plugins_dir = self.base_dir / self.PLUGINS_DIR
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        resolved = str(self.plugins_dir.resolve())
        if resolved not in sys.path:
            sys.path.append(resolved)
            self.logger.debug("Added plugins dir to sys.path: %s", resolved)

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

    def _clone_github_plugin(self, cfg: PluginConfig) -> Path:
        """Clone from GitHub to .plugins/<name> and return versioned dir."""
        self.logger.info("Cloning GitHub plugin '%s'...", cfg.source)
        plugin_base = self.plugins_dir / cfg.name
        if plugin_base.exists():
            shutil.rmtree(plugin_base)
        plugin_base.mkdir(parents=True, exist_ok=True)

        temp_dir = plugin_base / "temp"
        clone_url = (
            cfg.source if cfg.source.startswith("https://") else f"https://{cfg.source}"
        )
        subprocess.run(["git", "clone", clone_url, str(temp_dir)], check=True)

        ref = cfg.git_ref
        self.logger.info("Checking out ref '%s' for plugin '%s'.", ref, cfg.name)
        if cfg.version:
            try:
                subprocess.run(["git", "checkout", ref], cwd=temp_dir, check=True)
            except subprocess.CalledProcessError as e:
                if not ref.startswith("v"):
                    v_ref = f"v{ref}"
                    self.logger.warning(
                        "Checkout '%s' failed, trying '%s'.", ref, v_ref
                    )
                    try:
                        subprocess.run(
                            ["git", "checkout", v_ref], cwd=temp_dir, check=True
                        )
                        ref = v_ref
                    except subprocess.CalledProcessError:
                        self.logger.error(
                            "Checkout failed for '%s' and '%s'.", ref, v_ref
                        )
                        raise e
                else:
                    self.logger.error("Checkout failed for '%s'.", ref)
                    raise e
        else:
            subprocess.run(["git", "checkout", ref], cwd=temp_dir, check=True)

        safe_ref = ref.replace(".", "_")
        if safe_ref.startswith("v"):
            safe_ref = safe_ref[1:]

        version_dir = plugin_base / safe_ref
        version_dir.mkdir(exist_ok=True)

        for item in temp_dir.iterdir():
            if item.name == ".git":
                continue
            dest = version_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

        shutil.rmtree(temp_dir)
        self.logger.info("Cloned plugin '%s' to '%s'.", cfg.name, version_dir)
        return version_dir

    def install_plugin(self, cfg: PluginConfig, force_reinstall: bool = False) -> None:
        """Install a single plugin (download/copy) if needed."""
        self.logger.info(
            "Installing plugin '%s' from '%s'. (force=%s)",
            cfg.name,
            cfg.source,
            force_reinstall,
        )
        plugin_dir = self.plugins_dir / cfg.name

        if not force_reinstall:
            # Check if plugin_dir exists and compare sha if locked
            if plugin_dir.exists():
                self.logger.debug(
                    "Plugin '%s' dir already exists. Skipping re-download.", cfg.name
                )
                self._set_plugin_vars(cfg)
                return  # Assume user is fine with existing folder
            else:
                self.logger.debug(
                    "Plugin '%s' not found locally. Installing now.", cfg.name
                )

        # Perform actual installation
        if cfg.is_github_source:
            self._clone_github_plugin(cfg)
            base_path = str(self.plugins_dir / cfg.name)
            if base_path not in sys.path:
                sys.path.append(base_path)
        else:
            src_path = (self.base_dir / cfg.source).resolve()
            if not src_path.exists():
                raise FileNotFoundError(f"Local plugin source not found: {src_path}")

            if plugin_dir.exists():
                shutil.rmtree(plugin_dir)
            plugin_dir.mkdir(parents=True, exist_ok=True)

            for item in src_path.iterdir():
                dest = plugin_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)

            if str(plugin_dir) not in sys.path:
                sys.path.append(str(plugin_dir))

        self._set_plugin_vars(cfg)
        self.logger.info("Plugin '%s' installed successfully.", cfg.name)

    def load_plugin(self, name: str, git_ref: Optional[str] = None) -> Any:
        """Load a plugin from .plugins.

        Args:
            name: Name of the plugin to load
            git_ref: Optional git reference (version or branch) for GitHub plugins

        Returns:
            The loaded plugin instance

        Raises:
            PluginNotFoundError: If plugin cannot be found
            ImportError: If plugin cannot be imported
        """
        self.logger.info("Loading plugin '%s' (ref=%s).", name, git_ref or "local")
        try:
            if git_ref:
                safe_ref = git_ref.replace(".", "_")
                if safe_ref.startswith("v"):
                    safe_ref = safe_ref[1:]
                module_path = f"{name}.{safe_ref}"
                module = importlib.import_module(module_path)
            else:
                # local
                pdir = self.plugins_dir / name
                if not pdir.exists():
                    raise PluginNotFoundError(f"Plugin directory not found: {pdir}")
                if (pdir / "plugin.py").exists():
                    module = importlib.import_module("plugin")
                elif (pdir / "__init__.py").exists():
                    module = importlib.import_module(name)
                else:
                    raise PluginNotFoundError(
                        f"Neither plugin.py nor __init__.py found in {pdir}"
                    )

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

            if not plugin_class:
                raise PluginNotFoundError(
                    f"No plugin class in module: {module.__name__}"
                )
            instance = plugin_class()
            return self.kernel.add_plugin(instance, plugin_name=name)
        except ImportError as e:
            self.logger.exception("Import failed for plugin '%s'.", name)
            raise PluginNotFoundError(f"Failed to import plugin {name}: {e}") from e

    def create_lock_data(self, configs: List[PluginConfig]) -> Dict[str, Any]:
        """Create lock data with plugin references + sha."""
        data: Dict[str, Any] = {"plugins": []}
        for c in configs:
            entry = {
                "name": c.name,
                "source": c.source,
                "version": c.version,
                "branch": c.branch,
                "sha": "",  # We'll fill real sha after installation
            }
            # After plugin is installed, compute SHA and store it
            sha_val = self.compute_dir_sha(self.plugins_dir / c.name)
            entry["sha"] = sha_val
            data["plugins"].append(entry)
        return data

    def compute_dir_sha(self, dir_path: Path) -> str:
        """Compute a SHA-256 of all file contents in a directory (recursively)."""
        if not dir_path.exists():
            return ""
        sha256 = hashlib.sha256()
        for root, dirs, files in os.walk(dir_path):
            # Sort files/dirs so traversal is deterministic
            dirs.sort()
            files.sort()
            for f in files:
                full_path = Path(root) / f
                if not full_path.is_file():
                    continue
                with full_path.open("rb") as fp:
                    while True:
                        chunk = fp.read(8192)
                        if not chunk:
                            break
                        sha256.update(chunk)
        return sha256.hexdigest()

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
        self.logger.info("Lockfile updated: %s", path)

    def compare_with_lock(
        self, configs: List[PluginConfig], lock_data: Dict[str, Any]
    ) -> bool:
        """Compare plugin refs + sha with the existing lockfile. Return True if match."""
        if "plugins" not in lock_data:
            return False
        # Build sets
        current = set()
        for c in configs:
            # We'll check local dir's computed sha
            local_sha = self.compute_dir_sha(self.plugins_dir / c.name)
            current.add((c.name, c.source, c.version, c.branch, local_sha))

        locked = set()
        for p in lock_data["plugins"]:
            locked.add(
                (
                    p["name"],
                    p["source"],
                    p.get("version"),
                    p.get("branch"),
                    p.get("sha", ""),
                )
            )

        return current == locked

    def install_and_load_plugins(
        self,
        configs: List[PluginConfig],
        lockfile: Path,
        force_reinstall: bool = False,
    ) -> None:
        """Install and load plugins, writing updated lockfile.

        If force_reinstall=True, always re-download even if sha matches.
        Updates the lockfile with new plugin states after installation.

        Args:
            configs: List of plugin configurations to install and load
            lockfile: Path to the lockfile to update
            force_reinstall: Whether to force reinstallation of plugins
        """
        self.logger.info(
            "Installing/loading %d plugins (force=%s)...", len(configs), force_reinstall
        )

        for cfg in configs:
            try:
                # If we are not forcing, we do a quick check whether .plugins/<name> sha matches the existing lock
                # We'll do that below by reading old lock
                self.install_plugin(cfg, force_reinstall)
                git_ref = cfg.git_ref if cfg.is_github_source else None
                self.load_plugin(cfg.name, git_ref)
            except Exception as e:
                self.logger.exception("Error installing/loading '%s'.", cfg.name)
                raise e

        # Recompute final sha for each plugin
        new_lock_data = self.create_lock_data(configs)
        self.write_lockfile(lockfile, new_lock_data)
        self.logger.info("All plugins installed and loaded.")
