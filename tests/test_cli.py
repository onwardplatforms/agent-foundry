"""Tests for the CLI module."""

import json
import os
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from agent_foundry import __version__
from agent_foundry.cli.cli import cli
from agent_foundry.constants import AGENTS_DIR, DEFAULT_SYSTEM_PROMPT


@pytest.fixture
def runner() -> CliRunner:
    """Provide a Click CLI test runner."""
    return CliRunner()


@pytest.fixture(autouse=True)
def mock_openai() -> Generator[MagicMock, None, None]:
    """Mock OpenAI service for all tests."""
    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}),
        patch("semantic_kernel.connectors.ai.open_ai.OpenAIChatCompletion") as mock,
    ):
        yield mock


def test_version(runner):
    """Test the version command."""
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_add_with_random_id(runner: CliRunner, tmp_path: Path) -> None:
    """Test that add command works with a random ID."""
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["agents", "add"])
        assert result.exit_code == 0
        assert "Created new agent:" in result.output
        assert "config.json" in result.output

        # Check config file was created with default prompt
        agents_dir = Path(AGENTS_DIR)
        config_files = list(agents_dir.glob("*/config.json"))
        assert len(config_files) == 1

        with open(config_files[0]) as f:
            config = json.load(f)
            assert config["system_prompt"] == DEFAULT_SYSTEM_PROMPT


def test_add_with_specific_name(runner: CliRunner, tmp_path: Path) -> None:
    """Test that add command works with a specific name."""
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["agents", "add", "test-agent"])
        assert result.exit_code == 0
        assert "Created new agent: test-agent" in result.output

        config_path = Path(AGENTS_DIR) / "test-agent" / "config.json"
        assert config_path.exists()


def test_add_with_custom_system_prompt(runner: CliRunner, tmp_path: Path) -> None:
    """Test that add command works with a custom system prompt."""
    custom_prompt = "You are a test assistant."
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["agents", "add", "--system-prompt", custom_prompt])
        assert result.exit_code == 0

        agents_dir = Path(AGENTS_DIR)
        config_files = list(agents_dir.glob("*/config.json"))
        assert len(config_files) == 1

        with open(config_files[0]) as f:
            config = json.load(f)
            assert config["system_prompt"] == custom_prompt


def test_add_with_debug_flag(runner: CliRunner, tmp_path: Path) -> None:
    """Test that add command works with debug flag."""
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["--debug", "agents", "add"])
        assert result.exit_code == 0
        assert "Debug mode enabled" in result.output
        assert "Created new agent:" in result.output


def test_run_command(runner: CliRunner, tmp_path: Path) -> None:
    """Test that run command works."""
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Create an agent first
        result = runner.invoke(cli, ["agents", "add", "test-agent"])
        assert result.exit_code == 0

        # Mock the chat method to avoid actual API calls
        async def mock_async_chat(*args: Any, **kwargs: Any) -> str:
            return "Test response"

        with patch("agent_foundry.agent.Agent.chat", mock_async_chat):
            # Test running the agent
            result = runner.invoke(cli, ["agents", "run", "test-agent"], input="exit\n")
            assert result.exit_code == 0
            assert "Starting session with agent: test-agent" in result.output


def test_list_command_verbose(runner: CliRunner, tmp_path: Path) -> None:
    """Test that list command works with verbose flag."""
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Create an agent first
        result = runner.invoke(cli, ["agents", "add", "test-agent"])
        assert result.exit_code == 0  # Ensure creation succeeded

        # Test verbose listing
        result = runner.invoke(cli, ["agents", "list", "--verbose"])
        assert result.exit_code == 0
        assert "Available agents:" in result.output
        assert "test-agent:" in result.output
        assert "System prompt:" in result.output
        assert DEFAULT_SYSTEM_PROMPT in result.output


def test_list_command(runner: CliRunner, tmp_path: Path) -> None:
    """Test that list command works."""
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Create an agent first
        result = runner.invoke(cli, ["agents", "add", "test-agent"])
        assert result.exit_code == 0  # Ensure creation succeeded

        result = runner.invoke(cli, ["agents", "list"])
        assert result.exit_code == 0
        assert "Available agents:" in result.output
        assert "test-agent" in result.output


def test_remove_command_with_confirmation(runner: CliRunner, tmp_path: Path) -> None:
    """Test that remove command works with confirmation."""
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Create an agent first
        result = runner.invoke(cli, ["agents", "add", "test-agent"])
        assert result.exit_code == 0  # Ensure creation succeeded

        result = runner.invoke(cli, ["agents", "remove", "test-agent"], input="y\n")
        assert result.exit_code == 0
        assert "Deleted agent: test-agent" in result.output

        # Verify agent directory is gone
        agent_dir = Path(AGENTS_DIR) / "test-agent"
        assert not agent_dir.exists()


def test_remove_command_abort(runner: CliRunner, tmp_path: Path) -> None:
    """Test that remove command can be aborted."""
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Create an agent first
        result = runner.invoke(cli, ["agents", "add", "test-agent"])
        assert result.exit_code == 0  # Ensure creation succeeded

        result = runner.invoke(cli, ["agents", "remove", "test-agent"], input="n\n")
        assert result.exit_code == 0
        assert "Deleted agent: test-agent" not in result.output

        # Verify agent directory still exists
        agent_dir = Path(AGENTS_DIR) / "test-agent"
        assert agent_dir.exists()
