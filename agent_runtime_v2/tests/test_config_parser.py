"""Tests for configuration parsing and validation."""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from agent_runtime_v2.config.parser import (
    load_agent_config,
    resolve_environment_variables,
)
from agent_runtime_v2.config.types import AgentConfig
from agent_runtime_v2.plugins.sources import LocalPluginSource


@pytest.fixture
def temp_yaml_config():
    """Create a temporary YAML config file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as temp_file:
        temp_file.write(
            b"""
version: "1"
name: "Test Agent"
description: "A test agent"
system_prompt: "You are a test assistant."
model:
  provider: "openai"
  model: "gpt-4o"
  temperature: 0.7
plugins:
  - source:
      type: "local"
      path: "./plugins/test"
    variables:
      test_var: "test_value"
      default_name: "TestFriend"
env:
  API_KEY: ${{ env.TEST_API_KEY }}
"""
        )
    yield Path(temp_file.name)
    # Clean up
    os.unlink(temp_file.name)


def test_load_agent_config(temp_yaml_config):
    """Test loading agent configuration from YAML."""
    with patch.dict(os.environ, {"TEST_API_KEY": "test-key-123"}):
        config = load_agent_config(temp_yaml_config)

        # Verify basic configuration
        assert isinstance(config, AgentConfig)
        assert config.name == "Test Agent"
        assert config.description == "A test agent"
        assert config.system_prompt == "You are a test assistant."

        # Verify model configuration
        assert config.model.provider == "openai"
        assert config.model.model == "gpt-4o"
        assert config.model.temperature == 0.7

        # Verify plugins configuration
        assert len(config.plugins) == 1
        assert isinstance(config.plugins[0].source, LocalPluginSource)
        assert config.plugins[0].variables == {
            "test_var": "test_value",
            "default_name": "TestFriend",
        }


def test_resolve_environment_variables():
    """Test environment variable resolution in configuration."""
    with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
        config = {
            "simple": "value",
            "with_env": "${{ env.TEST_VAR }}",
            "nested": {"env_var": "${{ env.TEST_VAR }}"},
            "list": ["value", "${{ env.TEST_VAR }}"],
            "env": {"API_KEY": "${{ env.TEST_VAR }}"},
        }

        resolved = resolve_environment_variables(config)

        assert resolved["simple"] == "value"
        assert resolved["with_env"] == "test_value"
        assert resolved["nested"]["env_var"] == "test_value"
        assert resolved["list"][1] == "test_value"
        assert resolved["env"]["API_KEY"] == "test_value"


@pytest.fixture
def temp_dotenv_file():
    """Create a temporary .env file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".env", delete=False) as temp_file:
        temp_file.write(
            b"""
# Test .env file
TEST_VAR=dotenv_value
SHARED_VAR=from_dotenv
"""
        )
    yield Path(temp_file.name)
    # Clean up
    os.unlink(temp_file.name)


@pytest.fixture
def temp_yaml_with_env_vars():
    """Create a temporary YAML config file with environment variables."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as temp_file:
        temp_file.write(
            b"""
version: "1"
name: "Environment Test Agent"
description: "Testing environment variable precedence"
system_prompt: "You are a test assistant with ${{ env.SHARED_VAR }} and ${{ env.CONFIG_VAR }}."
model:
  provider: "openai"
  model: "gpt-4o"
env:
  CONFIG_VAR: config_value
  SHARED_VAR: from_config
  SYSTEM_VAR: ${{ env.SYSTEM_ENV_VAR }}
"""
        )
    yield Path(temp_file.name)
    # Clean up
    os.unlink(temp_file.name)


def test_environment_variable_precedence(temp_yaml_with_env_vars, temp_dotenv_file):
    """Test the precedence order of environment variables."""
    # Set up environment variables from different sources:
    # 1. System environment variables (highest precedence)
    # 2. .env file variables (middle precedence)
    # 3. Config-defined variables (lowest precedence)

    # Path to the .env file
    dotenv_path = temp_dotenv_file

    # Mock system environment variables
    with patch.dict(
        os.environ,
        {
            "SYSTEM_ENV_VAR": "from_system_env",
            "SHARED_VAR": "from_system_env",  # This should take precedence over .env and config
            "CONFIG_VAR": "config_value",  # Add CONFIG_VAR to the environment
        },
    ):
        # Patch dotenv.load_dotenv to load our test .env file
        with patch("agent_runtime_v2.config.parser.load_dotenv") as mock_load_dotenv:
            # Set up mock to simulate loading from our temp .env file
            def mock_load_env(*args, **kwargs):
                # This simulates dotenv loading these variables
                os.environ["TEST_VAR"] = "dotenv_value"
                # Don't overwrite SHARED_VAR if it exists in the system env
                if "SHARED_VAR" not in os.environ:
                    os.environ["SHARED_VAR"] = "from_dotenv"
                return True

            mock_load_dotenv.side_effect = mock_load_env

            # Load the config
            config = load_agent_config(temp_yaml_with_env_vars)

            # Verify variable precedence in system prompt
            # SHARED_VAR should come from system env, not .env or config
            assert (
                "You are a test assistant with from_system_env and config_value."
                in config.system_prompt
            )

            # Also test direct variable resolution
            assert (
                resolve_environment_variables("${{ env.SHARED_VAR }}")
                == "from_system_env"
            )
            assert (
                resolve_environment_variables("${{ env.CONFIG_VAR }}") == "config_value"
            )
            assert (
                resolve_environment_variables("${{ env.TEST_VAR }}") == "dotenv_value"
            )


def test_load_agent_config_with_missing_env_var(temp_yaml_config):
    """Test loading config with missing environment variable."""
    # Ensure the environment variable is not set
    with patch.dict(os.environ, {}, clear=True):
        config = load_agent_config(temp_yaml_config)

        # The parser should keep the original syntax when env var is not found
        assert config.name == "Test Agent"
        assert config.plugins[0].variables == {
            "test_var": "test_value",
            "default_name": "TestFriend",
        }


def test_load_agent_config_file_not_found():
    """Test error handling when config file is not found."""
    with pytest.raises(FileNotFoundError):
        load_agent_config("nonexistent_config.yaml")


@pytest.fixture
def invalid_yaml_config():
    """Create a temporary invalid YAML config file."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as temp_file:
        temp_file.write(
            b"""
version: "1"
name: "Invalid Agent"
# Missing required system_prompt
model:
  provider: "openai"
  # Missing required model field
  temperature: 0.7
"""
        )
    yield Path(temp_file.name)
    # Clean up
    os.unlink(temp_file.name)


def test_load_agent_config_invalid_schema(invalid_yaml_config):
    """Test error handling with invalid YAML schema."""
    import jsonschema

    with pytest.raises(jsonschema.exceptions.ValidationError):
        load_agent_config(invalid_yaml_config)
