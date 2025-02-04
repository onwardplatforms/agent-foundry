"""Tests for environment variable handling."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_foundry.env import get_env_var, load_env_files


@pytest.fixture
def mock_env_files(tmp_path: Path) -> Path:
    """Create mock environment files for testing."""
    # Create root .env
    root_env = tmp_path / ".env"
    root_env.write_text("OPENAI_MODEL=gpt-3.5-turbo\n" "SHARED_VAR=root\n")

    # Create agent-specific .env
    agent_dir = tmp_path / ".agents" / "test-agent"
    agent_dir.mkdir(parents=True)
    agent_env = agent_dir / ".env"
    agent_env.write_text("OPENAI_MODEL=gpt-4\n" "SHARED_VAR=agent\n" "AGENT_VAR=test\n")

    return tmp_path


def test_load_env_files_root_only(mock_env_files: Path) -> None:
    """Test loading only root .env file."""
    with patch("agent_foundry.env.Path") as mock_path:
        mock_path.return_value = mock_env_files / ".env"
        load_env_files()
        assert os.getenv("OPENAI_MODEL") == "gpt-3.5-turbo"
        assert os.getenv("SHARED_VAR") == "root"
        assert os.getenv("AGENT_VAR") is None


def test_load_env_files_with_agent(mock_env_files: Path) -> None:
    """Test loading both root and agent .env files."""
    with patch("agent_foundry.env.Path") as mock_path:

        def path_side_effect(path: str) -> Path:
            if path == ".env":
                return mock_env_files / ".env"
            return mock_env_files / path

        mock_path.side_effect = path_side_effect
        load_env_files("test-agent")
        assert os.getenv("OPENAI_MODEL") == "gpt-4"  # Agent value overrides root
        assert os.getenv("SHARED_VAR") == "agent"  # Agent value overrides root
        assert os.getenv("AGENT_VAR") == "test"  # Agent-specific var


def test_get_env_var_precedence() -> None:
    """Test environment variable precedence."""
    # Test system environment variable (highest priority)
    with patch.dict(os.environ, {"TEST_VAR": "system"}):
        with patch("agent_foundry.env.load_env_files") as mock_load:
            assert get_env_var("TEST_VAR", "default") == "system"
            mock_load.assert_not_called()

    # Test with agent ID
    with patch("agent_foundry.env.load_env_files") as mock_load:
        get_env_var("TEST_VAR", "default", "test-agent")
        mock_load.assert_called_once_with("test-agent")

    # Test default value (lowest priority)
    with patch("agent_foundry.env.load_env_files"):
        assert get_env_var("NONEXISTENT_VAR", "default") == "default"


def test_get_env_var_no_default() -> None:
    """Test getting environment variable without default."""
    with patch("agent_foundry.env.load_env_files"):
        assert get_env_var("NONEXISTENT_VAR") is None
