"""Tests for plugin variables functionality and integration with YAML configuration."""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
import asyncio
import inspect

from agent_runtime_v2.plugins.base import Plugin, PluginVariable
from agent_runtime_v2.plugins.sources import LocalPluginSource
from agent_runtime_v2.plugins.manager import PluginManager
from agent_runtime_v2.config.parser import load_agent_config


class MockPlugin(Plugin):
    """Test plugin class with variables."""

    name = "test_plugin"
    description = "A test plugin"
    plugin_instructions = "Test plugin instructions"

    # Define plugin variables as class attributes
    string_var = PluginVariable(
        type=str, description="A string variable", default="default string"
    )

    int_var = PluginVariable(type=int, description="An integer variable", default=42)

    bool_var = PluginVariable(
        type=bool, description="A boolean variable", default=False
    )

    # Not required anymore - has a default
    required_var = PluginVariable(
        type=str,
        description="A variable with a default value",
        default="default required",
    )

    async def handle_message(self, message, context):
        """Handle a message from the agent."""
        return f"Test plugin received: {message}"


@pytest.fixture
def plugin_yaml_config():
    """Create a temporary YAML config with plugin variables."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as temp_file:
        temp_file.write(
            b"""
version: "1"
name: "Plugin Variables Test Agent"
description: "A test agent for plugin variables"
system_prompt: "You are a test assistant."
model:
  provider: "openai"
  model: "gpt-4o"
  temperature: 0.7
plugins:
  - source:
      type: "local"
      path: "./mock_plugin_path"
    variables:
      string_var: "overridden string"
      int_var: 100
      bool_var: true
      required_var: "provided value"
"""
        )
    yield Path(temp_file.name)
    # Clean up
    os.unlink(temp_file.name)


@pytest.mark.asyncio
async def test_plugin_variable_defaults():
    """Test that plugin variables use defaults when not overridden."""
    # Create plugin instance without providing variables
    plugin = MockPlugin()

    # Variables should use defaults
    assert plugin.string_var == "default string"
    assert plugin.int_var == 42
    assert plugin.bool_var is False
    assert plugin.required_var == "default required"


@pytest.mark.asyncio
async def test_plugin_variable_override():
    """Test overriding plugin variables during initialization."""
    # Create plugin instance with overridden variables
    plugin = MockPlugin(
        string_var="custom string",
        int_var=99,
        bool_var=True,
        required_var="required value",
    )

    # Variables should use the provided values
    assert plugin.string_var == "custom string"
    assert plugin.int_var == 99
    assert plugin.bool_var is True
    assert plugin.required_var == "required value"


@pytest.mark.asyncio
async def test_plugin_manager_variables():
    """Test that PluginManager passes variables to plugins."""
    # Create a plugin manager
    plugin_manager = PluginManager()

    # Create a mock source that returns our MockPlugin class
    source = MagicMock(spec=LocalPluginSource)
    source.load.return_value = MockPlugin

    # Create variables dict
    variables = {
        "string_var": "manager string",
        "int_var": 123,
        "bool_var": True,
        "required_var": "manager required",
    }

    # Load the plugin with variables
    plugin = await plugin_manager.load_plugin(source, variables)

    # Check that variables were passed correctly
    assert plugin.string_var == "manager string"
    assert plugin.int_var == 123
    assert plugin.bool_var is True
    assert plugin.required_var == "manager required"


@pytest.mark.asyncio
async def test_yaml_config_plugin_variables(plugin_yaml_config):
    """Test integration of YAML configuration with plugin variables."""
    # Patch the entire LocalPluginSource.load method
    with patch(
        "agent_runtime_v2.plugins.sources.LocalPluginSource.load",
        return_value=MockPlugin,
    ):
        # Patch os.path.isabs to avoid path resolution issues
        with patch("os.path.isabs", return_value=True):
            # Load the agent config from YAML
            agent_config = load_agent_config(plugin_yaml_config)

            # Create a plugin manager
            plugin_manager = PluginManager()

            # Load the plugin using the config
            plugin_config = agent_config.plugins[0]
            plugin = await plugin_manager.load_plugin(
                plugin_config.source, plugin_config.variables
            )

            # Check that variables from YAML were applied correctly
            assert plugin.string_var == "overridden string"
            assert plugin.int_var == 100
            assert plugin.bool_var is True
            assert plugin.required_var == "provided value"


@pytest.mark.asyncio
async def test_yaml_config_partial_variables(plugin_yaml_config):
    """Test with only some variables specified in YAML."""

    # Create a MockPlugin subclass with additional variables
    class ExtendedMockPlugin(MockPlugin):
        extra_var = PluginVariable(
            type=str, description="An extra variable", default="extra default"
        )

    # Patch the LocalPluginSource.load method to return our ExtendedMockPlugin
    with patch(
        "agent_runtime_v2.plugins.sources.LocalPluginSource.load",
        return_value=ExtendedMockPlugin,
    ):
        # Patch os.path.isabs to avoid path resolution issues
        with patch("os.path.isabs", return_value=True):
            # Load the agent config from YAML
            agent_config = load_agent_config(plugin_yaml_config)

            # Create a plugin manager
            plugin_manager = PluginManager()

            # Load the plugin using the config
            plugin_config = agent_config.plugins[0]
            plugin = await plugin_manager.load_plugin(
                plugin_config.source, plugin_config.variables
            )

            # Check that variables from YAML were applied correctly
            assert plugin.string_var == "overridden string"
            assert plugin.int_var == 100
            assert plugin.bool_var is True
            assert plugin.required_var == "provided value"
            # Check that unspecified variables use defaults
            assert plugin.extra_var == "extra default"
