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
    root_env.write_text(
        "OPENAI_MODEL=gpt-3.5-turbo\n" "OPENAI_API_KEY=global-key\n" "SHARED_VAR=root\n"
    )

    # Create agent-specific .env
    agent_dir = tmp_path / ".agents" / "test-agent"
    agent_dir.mkdir(parents=True)
    agent_env = agent_dir / ".env"
    agent_env.write_text(
        "OPENAI_MODEL=gpt-4\n"
        "OPENAI_API_KEY=agent-key\n"
        "SHARED_VAR=agent\n"
        "AGENT_VAR=test\n"
    )

    return tmp_path


def test_load_env_files_root_only(mock_env_files: Path) -> None:
    """Test loading only root .env file."""
    with patch.dict(os.environ, {}, clear=True):
        with patch("agent_foundry.env.Path") as mock_path:
            mock_path.return_value = mock_env_files / ".env"
            load_env_files()
            assert os.getenv("OPENAI_MODEL") == "gpt-3.5-turbo"
            assert os.getenv("OPENAI_API_KEY") == "global-key"
            assert os.getenv("SHARED_VAR") == "root"
            assert os.getenv("AGENT_VAR") is None


def test_load_env_files_with_agent(mock_env_files: Path) -> None:
    """Test loading both root and agent .env files."""
    with patch.dict(os.environ, {}, clear=True):
        with patch("agent_foundry.env.Path") as mock_path:

            def path_side_effect(path: str) -> Path:
                if path == ".env":
                    return mock_env_files / ".env"
                return mock_env_files / path

            mock_path.side_effect = path_side_effect
            load_env_files("test-agent")
            assert os.getenv("OPENAI_MODEL") == "gpt-4"  # Agent value overrides root
            assert (
                os.getenv("OPENAI_API_KEY") == "agent-key"
            )  # Agent value overrides root
            assert os.getenv("SHARED_VAR") == "agent"  # Agent value overrides root
            assert os.getenv("AGENT_VAR") == "test"  # Agent-specific var


def test_get_env_var_precedence(mock_env_files: Path) -> None:
    """Test environment variable precedence."""
    with patch.dict(os.environ, {}, clear=True):
        with patch("agent_foundry.env.Path") as mock_path:

            def path_side_effect(path: str) -> Path:
                if path == ".env":
                    return mock_env_files / ".env"
                return mock_env_files / path

            mock_path.side_effect = path_side_effect

            # Test with agent ID (highest priority)
            assert get_env_var("OPENAI_MODEL", None, "test-agent") == "gpt-4"
            assert get_env_var("OPENAI_API_KEY", None, "test-agent") == "agent-key"

            # Clear environment for next test
            os.environ.clear()

            # Test with root .env (medium priority)
            assert get_env_var("OPENAI_MODEL") == "gpt-3.5-turbo"
            assert get_env_var("OPENAI_API_KEY") == "global-key"

            # Clear environment for next test
            os.environ.clear()

            # Test default value (lowest priority)
            assert get_env_var("NONEXISTENT_VAR", "default") == "default"


def test_get_env_var_no_default() -> None:
    """Test getting environment variable without default."""
    with patch.dict(os.environ, {}, clear=True):
        assert get_env_var("NONEXISTENT_VAR") is None
