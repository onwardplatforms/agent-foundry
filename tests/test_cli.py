"""Tests for the Agent Foundry CLI."""

import pytest
from click.testing import CliRunner

from agent_foundry.cli.commands import cli


@pytest.fixture
def runner() -> CliRunner:
    """Provide a Click CLI test runner."""
    return CliRunner()


def test_create_with_random_id(runner: CliRunner) -> None:
    """Test that create command works with a random ID."""
    result = runner.invoke(cli, ["create"])
    assert result.exit_code == 0
    assert "Creating new agent:" in result.output


def test_create_with_specific_name(runner: CliRunner) -> None:
    """Test that create command works with a specific name."""
    result = runner.invoke(cli, ["create", "test-agent"])
    assert result.exit_code == 0
    assert "Creating new agent: test-agent" in result.output


def test_create_with_debug_flag(runner: CliRunner) -> None:
    """Test that create command works with debug flag."""
    result = runner.invoke(cli, ["create", "--debug"])
    assert result.exit_code == 0
    assert "Debug mode enabled" in result.output
    assert "Creating new agent:" in result.output


def test_run_command(runner: CliRunner) -> None:
    """Test that run command works."""
    result = runner.invoke(cli, ["run", "test-agent"])
    assert result.exit_code == 0
    assert "Starting session with agent: test-agent" in result.output


def test_list_command(runner: CliRunner) -> None:
    """Test that list command works."""
    result = runner.invoke(cli, ["list"])
    assert result.exit_code == 0
    assert "Available agents:" in result.output


def test_delete_command_with_confirmation(runner: CliRunner) -> None:
    """Test that delete command works with confirmation."""
    result = runner.invoke(cli, ["delete", "test-agent"], input="y\n")
    assert result.exit_code == 0
    assert "Deleting agent: test-agent" in result.output


def test_delete_command_abort(runner: CliRunner) -> None:
    """Test that delete command can be aborted."""
    result = runner.invoke(cli, ["delete", "test-agent"], input="n\n")
    assert result.exit_code == 0
    assert "Deleting agent: test-agent" not in result.output
