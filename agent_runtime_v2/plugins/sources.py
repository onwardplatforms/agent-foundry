"""Plugin source handling system."""

import os
import sys
import tempfile
import shutil
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Type
import importlib.util
import subprocess

from .base import Plugin

logger = logging.getLogger(__name__)


@dataclass
class PluginSource(ABC):
    """Base class for plugin sources."""

    @abstractmethod
    def load(self) -> Type[Plugin]:
        """Load the plugin class from this source.

        Returns:
            The plugin class

        Raises:
            ImportError: If the plugin cannot be imported
            ValueError: If the plugin is invalid
        """
        pass


@dataclass
class LocalPluginSource(PluginSource):
    """A plugin source from the local filesystem."""

    path: Path

    def load(self) -> Type[Plugin]:
        """Load a plugin from a local path.

        The path can point to either:
        1. A .py file containing the plugin class
        2. A directory containing an __init__.py with the plugin class

        Returns:
            The plugin class

        Raises:
            ImportError: If the plugin cannot be imported
            ValueError: If the plugin is invalid
        """
        path = Path(self.path)
        logger.info(f"Loading plugin from local path: {path}")

        if not path.exists():
            logger.error(f"Plugin path does not exist: {path}")
            raise ImportError(f"Plugin path does not exist: {path}")

        if path.is_file() and path.suffix == ".py":
            module_path = path
            module_name = path.stem
            logger.info(f"Loading plugin from Python file: {module_path}")
        elif path.is_dir() and (path / "__init__.py").exists():
            module_path = path / "__init__.py"
            module_name = path.name
            logger.info(
                f"Loading plugin from directory with __init__.py: {module_path}"
            )
        else:
            logger.error(
                f"Plugin path must be a .py file or directory with __init__.py: {path}"
            )
            raise ImportError(
                f"Plugin path must be a .py file or directory with __init__.py: {path}"
            )

        # Import the module
        logger.debug(f"Creating module spec from file: {module_path}")
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if not spec or not spec.loader:
            logger.error(f"Could not load plugin spec from: {module_path}")
            raise ImportError(f"Could not load plugin spec from: {module_path}")

        logger.debug(f"Creating module from spec: {spec}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        logger.debug(f"Executing module: {module_name}")
        try:
            spec.loader.exec_module(module)
            logger.info(f"Module executed successfully: {module_name}")
        except Exception as e:
            logger.error(f"Error executing module {module_name}: {e}", exc_info=e)
            raise ImportError(f"Error executing module {module_name}: {e}") from e

        # Find the plugin class
        logger.debug(f"Searching for Plugin subclass in module: {module_name}")
        plugin_class = None
        for item_name in dir(module):
            item = getattr(module, item_name)
            logger.debug(f"Checking item: {item_name}, type: {type(item)}")
            if isinstance(item, type) and issubclass(item, Plugin) and item != Plugin:
                plugin_class = item
                logger.info(f"Found Plugin subclass: {item_name}")
                break

        if not plugin_class:
            logger.error(f"No Plugin subclass found in module: {module_path}")
            raise ValueError(f"No Plugin subclass found in module: {module_path}")

        logger.info(f"Successfully loaded plugin class: {plugin_class.__name__}")
        return plugin_class


@dataclass
class GitHubPluginSource(PluginSource):
    """A plugin source from a GitHub repository."""

    repo_url: str
    version_tag: str
    plugin_path: str
    cache_dir: Optional[Path] = None

    def __post_init__(self):
        """Set up the cache directory."""
        if self.cache_dir is None:
            self.cache_dir = Path(tempfile.gettempdir()) / "agent_plugins"

    def load(self) -> Type[Plugin]:
        """Load a plugin from a GitHub repository.

        Returns:
            The plugin class

        Raises:
            ImportError: If the plugin cannot be imported
            ValueError: If the plugin is invalid
        """
        logger.info(
            f"Loading plugin from GitHub: {self.repo_url} at {self.version_tag}"
        )

        # Create cache directory if it doesn't exist
        cache_dir = Path(self.cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Using cache directory: {cache_dir}")

        # Create a unique directory name for this repo+version
        repo_name = self.repo_url.split("/")[-1]
        cache_path = cache_dir / f"{repo_name}_{self.version_tag}"
        logger.debug(f"Cache path for this repo: {cache_path}")

        # Check if already cached
        if not cache_path.exists():
            logger.info(f"Repository not cached, cloning from GitHub")
            # Clone the repository
            try:
                logger.debug(
                    f"Running git clone for {self.repo_url} at {self.version_tag}"
                )
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--depth",
                        "1",
                        "--branch",
                        self.version_tag,
                        f"https://{self.repo_url}",
                        str(cache_path),
                    ],
                    check=True,
                    capture_output=True,
                )
                logger.info(f"Repository cloned successfully to {cache_path}")
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.decode()
                logger.error(f"Failed to clone repository: {error_msg}", exc_info=e)
                raise ImportError(
                    f"Failed to clone repository {self.repo_url} at {self.version_tag}: "
                    f"{error_msg}"
                )
        else:
            logger.info(f"Using cached repository at {cache_path}")

        # Load from the cached location
        plugin_path = cache_path / self.plugin_path
        logger.info(f"Loading plugin from path: {plugin_path}")
        return LocalPluginSource(plugin_path).load()
