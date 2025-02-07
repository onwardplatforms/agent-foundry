"""Tests for the plugin manager."""

import os
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import MagicMock, patch

import pytest
import semantic_kernel as sk

from agent_runtime.plugins.manager import PluginConfig, PluginManager


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
    @sk_function(
        description="A test function",
        name="test_function"
    )
    def test_function(self) -> str:
        return "Hello from plugin!"
"""
        )

    return plugin_dir


@pytest.fixture
def valid_plugin_config() -> Dict[str, Any]:
    """Create a valid plugin configuration."""
    return {
        "name": "example-plugin",
        "source": "github.com/example/plugin",
        "version": "v1.0.0",
        "variables": {"api_key": "$TEST_API_KEY"},
    }


def test_plugin_config_github_source(valid_plugin_config: Dict[str, Any]) -> None:
    """Test plugin configuration with GitHub source."""
    config = PluginConfig(**valid_plugin_config)
    assert config.is_github_source
    assert not config.is_local_source
    assert config.name == "example-plugin"
    assert config.version == "v1.0.0"


def test_plugin_config_local_source(valid_plugin_config: Dict[str, Any]) -> None:
    """Test plugin configuration with local source."""
    valid_plugin_config["source"] = "/path/to/local/plugin"
    config = PluginConfig(**valid_plugin_config)
    assert not config.is_github_source
    assert config.is_local_source


@pytest.fixture
def plugin_manager(plugins_dir: Path) -> PluginManager:
    """Create a plugin manager instance."""
    kernel = sk.Kernel()
    return PluginManager(kernel, plugins_dir)


def test_install_local_plugin(
    plugin_manager: PluginManager,
    example_plugin_dir: Path,
    valid_plugin_config: Dict[str, Any],
) -> None:
    """Test installation of a local plugin."""
    valid_plugin_config["source"] = str(example_plugin_dir)
    config = PluginConfig(**valid_plugin_config)

    plugin_manager.install_plugin(config)

    # Check plugin directory was created
    plugin_dir = plugin_manager.plugins_dir / config.name
    assert plugin_dir.exists()
    assert (plugin_dir / "plugin.py").exists()


@patch("subprocess.run")
def test_install_github_plugin(
    mock_run: MagicMock,
    plugin_manager: PluginManager,
    valid_plugin_config: Dict[str, Any],
) -> None:
    """Test installation of a GitHub plugin."""
    config = PluginConfig(**valid_plugin_config)

    # Mock successful git clone
    mock_run.return_value.returncode = 0

    plugin_manager.install_plugin(config)

    # Check git clone was called correctly
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "git"
    assert args[1] == "clone"
    assert args[2] == f"https://{config.source}"
    assert args[4] == str(plugin_manager.plugins_dir / config.name)


def test_plugin_variables(
    plugin_manager: PluginManager,
    example_plugin_dir: Path,
    valid_plugin_config: Dict[str, Any],
) -> None:
    """Test plugin variable handling."""
    valid_plugin_config["source"] = str(example_plugin_dir)
    config = PluginConfig(**valid_plugin_config)

    with patch.dict(os.environ, {"TEST_API_KEY": "test-key"}):
        plugin_manager.install_plugin(config)

        # Check environment variables were set
        assert os.environ["TEST_API_KEY"] == "test-key"


def test_load_plugin(
    plugin_manager: PluginManager,
    example_plugin_dir: Path,
    valid_plugin_config: Dict[str, Any],
) -> None:
    """Test loading a plugin into the kernel."""
    valid_plugin_config["source"] = str(example_plugin_dir)
    config = PluginConfig(**valid_plugin_config)

    # Install and load plugin
    plugin_manager.install_plugin(config)
    plugin = plugin_manager.load_plugin(config.name)

    # Check plugin was loaded correctly
    assert plugin is not None
    assert hasattr(plugin, "test_function")
    assert plugin.test_function() == "Hello from plugin!"


def test_load_nonexistent_plugin(plugin_manager: PluginManager) -> None:
    """Test loading a nonexistent plugin."""
    with pytest.raises(ValueError, match="Plugin not found"):
        plugin_manager.load_plugin("nonexistent-plugin")
