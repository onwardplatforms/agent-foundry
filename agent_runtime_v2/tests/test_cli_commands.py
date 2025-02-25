"""Tests for CLI commands functionality."""

import os
import pytest
import tempfile
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from agent_runtime_v2.cli.commands import cli, run
from agent_runtime_v2.utils import LogLevel


@pytest.fixture
def temp_agent_yaml():
    """Create a temporary agent YAML file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as temp_file:
        temp_file.write(
            b"""
version: "1"
name: "CLI Test Agent"
description: "A test agent for CLI commands"
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
      default_name: "CLIFriend"
"""
        )
    yield Path(temp_file.name)
    # Clean up
    os.unlink(temp_file.name)


def test_cli_command_help():
    """Test the CLI help command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "agently.run - Declarative AI agents without code" in result.output


def test_run_command_help():
    """Test the run command help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--help"])
    assert result.exit_code == 0
    assert "Run an agent from your configuration" in result.output


def test_run_command_missing_config():
    """Test run command with missing configuration file."""
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--agent", "nonexistent.yaml"])
    assert result.exit_code == 1
    assert "Error: Agent configuration file not found" in result.output


def test_run_command_with_config(temp_agent_yaml):
    """Test run command with a valid configuration file."""
    # We need to patch interactive_loop to avoid actual execution
    with (
        patch("agent_runtime_v2.cli.commands.interactive_loop") as mock_loop,
        patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-123"}),
    ):

        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--agent", str(temp_agent_yaml)])

        # Check that the command executed correctly
        assert result.exit_code == 0

        # Verify that interactive_loop was called with the correct config
        mock_loop.assert_called_once()
        agent_config = mock_loop.call_args[0][0]
        assert agent_config.name == "CLI Test Agent"
        assert agent_config.description == "A test agent for CLI commands"

        # Verify that plugin variables were loaded correctly
        assert len(agent_config.plugins) == 1
        assert agent_config.plugins[0].variables == {
            "test_var": "test_value",
            "default_name": "CLIFriend",
        }


def test_run_command_with_log_level(temp_agent_yaml):
    """Test run command with a specified log level."""
    # We need to patch both interactive_loop and configure_logging
    with (
        patch("agent_runtime_v2.cli.commands.interactive_loop") as mock_loop,
        patch("agent_runtime_v2.cli.commands.configure_logging") as mock_logging,
        patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-123"}),
    ):

        runner = CliRunner()
        result = runner.invoke(
            cli, ["run", "--agent", str(temp_agent_yaml), "--log-level", "debug"]
        )

        # Check that the command executed correctly
        assert result.exit_code == 0

        # Verify that configure_logging was called with DEBUG level
        mock_logging.assert_called_with(level=LogLevel.DEBUG)

        # Verify that interactive_loop was called
        mock_loop.assert_called_once()


def test_run_command_missing_openai_key(temp_agent_yaml):
    """Test run command with missing OpenAI API key."""
    # Mock the environment to ensure OPENAI_API_KEY is not present
    with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=True):
        # We need to patch sys.exit to prevent actual program termination
        with patch("sys.exit") as mock_exit:
            # Add patch for interactive_loop to avoid actual execution
            with patch("agent_runtime_v2.cli.commands.interactive_loop") as mock_loop:
                runner = CliRunner()
                result = runner.invoke(cli, ["run", "--agent", str(temp_agent_yaml)])

                # Check that sys.exit was called with exit code 1 at some point
                mock_exit.assert_any_call(1)

                # Check the error message was displayed
                assert (
                    "Error: OPENAI_API_KEY environment variable not set"
                    in result.output
                )
                assert (
                    "Please set it with: export OPENAI_API_KEY=your_key_here"
                    in result.output
                )
