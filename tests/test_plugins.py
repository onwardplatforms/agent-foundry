"""Tests for the plugin manager."""

import os
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
import semantic_kernel as sk

from agent_runtime.plugins.manager import (
    PluginConfig,
    PluginManager,
    PluginNotFoundError,
)


@pytest.fixture
def plugins_dir(tmp_path: Path) -> Path:
    """Create a temporary plugins directory."""
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    return plugins_dir


@pytest.fixture
def example_plugin_dir(tmp_path) -> Path:
    """Create a temporary plugin directory with required files."""
    plugin_dir = tmp_path / "example-plugin"
    plugin_dir.mkdir(parents=True)

    # Create plugin.py
    plugin_file = plugin_dir / "plugin.py"
    plugin_file.write_text(
        """
class ExamplePlugin:
    def __init__(self):
        self.test_function = self._test_function

    def _test_function(self) -> str:
        return "Hello from plugin!"
"""
    )
    return plugin_dir


@pytest.fixture
def valid_plugin_config() -> Dict[str, Any]:
    """Create a valid plugin configuration."""
    return {
        "source": "github.com/jsoconno/sk-test-plugin",
        "version": "main",
        "variables": {},
    }


def test_plugin_config_github_source(valid_plugin_config: Dict[str, Any]) -> None:
    """Test plugin configuration with GitHub source."""
    config = PluginConfig(
        plugin_type="remote", name="test_plugin", **valid_plugin_config
    )
    assert config.source == valid_plugin_config["source"]
    assert config.version == valid_plugin_config["version"]
    assert config.variables == valid_plugin_config["variables"]


@pytest.fixture
def config_dir(tmp_path):
    """Create a temporary directory for configuration files."""
    return tmp_path


def test_plugin_config_local_source(config_dir):
    """Test local plugin source configuration."""
    config = PluginConfig(
        plugin_type="local", name="example", source="./local_plugins/echo"
    )
    assert config.source == "./local_plugins/echo"
    assert config.name == "example"
    assert config.plugin_type == "local"


def test_plugin_config_validation(config_dir):
    """Test plugin configuration validation."""
    # Test invalid local source path
    with pytest.raises(
        ValueError, match="Local plugin paths must start with ./ or ../"
    ):
        PluginConfig(plugin_type="local", name="example", source="local_plugins/echo")

    # Test version with local plugin
    with pytest.raises(
        ValueError, match="Version cannot be specified for local plugins"
    ):
        PluginConfig(
            plugin_type="local",
            name="example",
            source="./local_plugins/echo",
            version="1.0.0",
        )


@pytest.fixture
def plugin_manager(plugins_dir: Path) -> PluginManager:
    """Create a plugin manager instance."""
    kernel = sk.Kernel()
    return PluginManager(plugins_dir, kernel)


def test_install_local_plugin(
    plugin_manager: PluginManager,
    example_plugin_dir: Path,
) -> None:
    """Test installation of a local plugin."""
    # Create the plugins directory
    plugins_dir = plugin_manager.plugins_dir
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Create a plugins directory in base_dir for local plugins
    local_plugins_dir = plugin_manager.base_dir / "plugins"
    local_plugins_dir.mkdir(parents=True, exist_ok=True)

    # Create a symlink to the example plugin in the local plugins directory
    target_dir = local_plugins_dir / "example"
    if not target_dir.exists():
        target_dir.symlink_to(example_plugin_dir, target_is_directory=True)

    config = PluginConfig(
        plugin_type="local", name="example", source="./plugins/example"
    )

    plugin_manager.install_plugin(config)

    # Check plugin directory exists
    assert target_dir.exists()
    assert (target_dir / "plugin.py").exists()


@patch("agent_runtime.plugins.manager.PluginManager._clone_github_plugin")
def test_install_github_plugin(
    mock_clone: MagicMock,
    plugin_manager: PluginManager,
    valid_plugin_config: Dict[str, Any],
) -> None:
    """Test installation of a GitHub plugin."""
    # Create the plugins directory
    plugins_dir = plugin_manager.plugins_dir
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Mock the clone operation
    def mock_clone_impl(cfg):
        plugin_dir = plugins_dir / cfg.name
        plugin_dir.mkdir(parents=True, exist_ok=True)
        version_dir = plugin_dir / cfg.version
        version_dir.mkdir(parents=True, exist_ok=True)
        (version_dir / "__init__.py").touch()

    mock_clone.side_effect = mock_clone_impl

    config = PluginConfig(
        plugin_type="remote", name="test_plugin", **valid_plugin_config
    )
    plugin_manager.install_plugin(config)

    # Check plugin directory was created
    plugin_dir = plugin_manager.plugins_dir / config.name
    assert plugin_dir.exists()
    assert (plugin_dir / config.version).exists()
    assert (plugin_dir / config.version / "__init__.py").exists()


def test_plugin_variables(
    plugin_manager: PluginManager,
    example_plugin_dir: Path,
) -> None:
    """Test plugin variable handling."""
    # Create the plugins directory
    plugins_dir = plugin_manager.plugins_dir
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Create a plugins directory in base_dir for local plugins
    local_plugins_dir = plugin_manager.base_dir / "plugins"
    local_plugins_dir.mkdir(parents=True, exist_ok=True)

    # Create a symlink to the example plugin in the local plugins directory
    target_dir = local_plugins_dir / "example"
    if not target_dir.exists():
        target_dir.symlink_to(example_plugin_dir, target_is_directory=True)

    config = PluginConfig(
        plugin_type="local",
        name="example",
        source="./plugins/example",
        variables={"api_key": "$TEST_API_KEY"},
    )

    with patch.dict(os.environ, {"TEST_API_KEY": "test-key"}):
        plugin_manager.install_plugin(config)
        assert os.environ["AGENT_VAR_API_KEY"] == "test-key"


@patch("importlib.import_module")
@patch("semantic_kernel.kernel.Kernel.add_plugin")
def test_load_plugin(
    mock_add_plugin: MagicMock,
    mock_import_module: MagicMock,
    plugin_manager: PluginManager,
    example_plugin_dir: Path,
) -> None:
    """Test loading a plugin into the kernel."""
    # Create the plugins directory
    plugins_dir = plugin_manager.plugins_dir
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Create a plugins directory in base_dir for local plugins
    local_plugins_dir = plugin_manager.base_dir / "plugins"
    local_plugins_dir.mkdir(parents=True, exist_ok=True)

    # Create a symlink to the example plugin in the local plugins directory
    target_dir = local_plugins_dir / "example"
    if not target_dir.exists():
        target_dir.symlink_to(example_plugin_dir, target_is_directory=True)

    # Create a mock module with the plugin class
    mock_module = MagicMock()
    mock_module.__name__ = "plugin"

    def kernel_function(description: str = ""):
        def decorator(func):
            func.__kernel_function__ = True
            func.__description__ = description
            return func

        return decorator

    class ExamplePlugin:
        def __init__(self):
            self.test_function = self._test_function

        @kernel_function(description="Test function")
        def _test_function(self) -> str:
            return "Hello from plugin!"

    # Set up the mock module
    ExamplePlugin.__module__ = "plugin"
    mock_module.ExamplePlugin = ExamplePlugin
    mock_import_module.return_value = mock_module

    # Mock the kernel's add_plugin to return the plugin instance
    mock_plugin_instance = ExamplePlugin()
    mock_add_plugin.return_value = mock_plugin_instance

    # Create a local plugin config
    config = PluginConfig(
        plugin_type="local", name="example", source="./plugins/example"
    )

    # Store the config in the manager using the scoped name
    plugin_manager.plugin_configs[config.scoped_name] = config

    # Install and load plugin
    plugin_manager.install_plugin(config)
    plugin = plugin_manager.load_plugin(config.scoped_name)

    # Check plugin was loaded correctly
    assert plugin is not None
    assert hasattr(plugin, "test_function")
    assert plugin.test_function() == "Hello from plugin!"


def test_load_nonexistent_plugin(plugin_manager: PluginManager) -> None:
    """Test loading a nonexistent plugin."""
    with pytest.raises(PluginNotFoundError, match="No configuration found for plugin"):
        plugin_manager.load_plugin("nonexistent-plugin")
