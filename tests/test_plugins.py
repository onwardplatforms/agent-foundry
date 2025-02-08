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
def example_plugin_dir(tmp_path: Path) -> Path:
    """Create an example plugin directory with a simple plugin."""
    plugin_dir = tmp_path / "example-plugin"
    plugin_dir.mkdir()

    # Create plugin.py
    with open(plugin_dir / "plugin.py", "w") as f:
        f.write(
            """
from semantic_kernel.skill_definition import sk_function

class ExamplePlugin:
    def __init__(self):
        self.test_function = self._test_function

    @sk_function(
        description="A test function",
        name="test_function"
    )
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
    config = PluginConfig(**valid_plugin_config)
    assert config.is_github_source
    assert not config.is_local_source
    assert config.name == "sk_test_plugin"
    assert config.version == "main"


def test_plugin_config_local_source(valid_plugin_config: Dict[str, Any]) -> None:
    """Test plugin configuration with local source."""
    # Remove version and update source for local plugin
    del valid_plugin_config["version"]
    valid_plugin_config["source"] = "/path/to/local/plugin"
    config = PluginConfig(**valid_plugin_config)
    assert not config.is_github_source
    assert config.is_local_source
    assert config.name == "plugin"


def test_plugin_config_validation() -> None:
    """Test plugin configuration validation."""
    # Test GitHub source requires version
    with pytest.raises(
        ValueError, match="Version must be specified for GitHub plugins"
    ):
        PluginConfig(source="github.com/user/repo")

    # Test local source cannot have version
    with pytest.raises(
        ValueError, match="Version cannot be specified for local plugins"
    ):
        PluginConfig(source="local/plugin", version="1.0.0")


@pytest.fixture
def plugin_manager(plugins_dir: Path) -> PluginManager:
    """Create a plugin manager instance."""
    kernel = sk.Kernel()
    return PluginManager(kernel, plugins_dir)


def test_install_local_plugin(
    plugin_manager: PluginManager,
    example_plugin_dir: Path,
) -> None:
    """Test installation of a local plugin."""
    config = PluginConfig(source=str(example_plugin_dir))

    plugin_manager.install_plugin(config)

    # Check plugin directory was created
    plugin_dir = plugin_manager.plugins_dir / config.name
    assert plugin_dir.exists()
    assert (plugin_dir / "plugin.py").exists()


def test_install_github_plugin(
    plugin_manager: PluginManager,
    valid_plugin_config: Dict[str, Any],
) -> None:
    """Test installation of a GitHub plugin."""
    config = PluginConfig(**valid_plugin_config)
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
    config = PluginConfig(
        source=str(example_plugin_dir), variables={"api_key": "$TEST_API_KEY"}
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
    # Create a mock module with the plugin class
    mock_module = MagicMock()
    mock_module.__name__ = "plugin"

    class ExamplePlugin:
        def __init__(self):
            self.test_function = self._test_function

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
    config = PluginConfig(source=str(example_plugin_dir))

    # Install and load plugin
    plugin_manager.install_plugin(config)
    plugin = plugin_manager.load_plugin(config.name)

    # Check plugin was loaded correctly
    assert plugin is not None
    assert hasattr(plugin, "test_function")
    assert plugin.test_function() == "Hello from plugin!"

    # Verify kernel.add_plugin was called correctly
    mock_add_plugin.assert_called_once()
    actual_instance = mock_add_plugin.call_args[0][0]
    assert isinstance(actual_instance, ExamplePlugin)
    assert actual_instance.test_function() == "Hello from plugin!"


def test_load_nonexistent_plugin(plugin_manager: PluginManager) -> None:
    """Test loading a nonexistent plugin."""
    with pytest.raises(PluginNotFoundError, match="Plugin directory not found"):
        plugin_manager.load_plugin("nonexistent-plugin")
