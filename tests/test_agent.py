"""Tests for Agent class."""

import json
from pathlib import Path
from typing import AsyncIterator, Generator
from unittest.mock import patch

import pytest
from semantic_kernel.contents import (
    AuthorRole,
    ChatHistory,
    StreamingChatMessageContent,
)

from agent_foundry.agent import Agent
from agent_foundry.provider_impl import Provider
from agent_foundry.providers import ProviderConfig, ProviderType


@pytest.fixture
def mock_agent_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a mock agent directory."""
    agent_dir = tmp_path / ".agents" / "test-agent"
    agent_dir.mkdir(parents=True)
    yield agent_dir


@pytest.fixture
def mock_config() -> ProviderConfig:
    """Create a mock provider config."""
    return ProviderConfig(
        name=ProviderType.OPENAI,
        model="gpt-4",
        settings={"temperature": 0.7},
    )


class MockProvider(Provider):
    """Mock provider for testing."""

    async def chat(
        self, history: ChatHistory
    ) -> AsyncIterator[StreamingChatMessageContent]:
        """Mock chat method."""
        yield StreamingChatMessageContent(
            role=AuthorRole.ASSISTANT,
            content="Mock response",
            choice_index=0,
        )


def test_agent_init(mock_config: ProviderConfig) -> None:
    """Test agent initialization."""
    with patch("agent_foundry.agent.load_env_files") as mock_load_env:
        with patch("agent_foundry.agent.get_provider") as mock_get_provider:
            mock_get_provider.return_value = MockProvider(mock_config)

            agent = Agent("test-agent", "Test prompt", mock_config)
            assert agent.id == "test-agent"
            assert agent.system_prompt == "Test prompt"
            assert isinstance(agent.provider, MockProvider)

            mock_load_env.assert_called_once_with("test-agent")
            mock_get_provider.assert_called_once()


def test_agent_init_default_provider() -> None:
    """Test agent initialization with default provider."""
    with patch("agent_foundry.agent.load_env_files"):
        with patch("agent_foundry.agent.get_provider") as mock_get_provider:
            mock_get_provider.return_value = MockProvider(
                ProviderConfig(name=ProviderType.OPENAI)
            )

            agent = Agent("test-agent", "Test prompt")
            assert isinstance(agent.provider, MockProvider)
            mock_get_provider.assert_called_once()


def test_agent_create(mock_agent_dir: Path, mock_config: ProviderConfig) -> None:
    """Test agent creation."""
    with patch("agent_foundry.agent.Path") as mock_path:
        mock_path.return_value = mock_agent_dir

        agent = Agent.create("test-agent", "Test prompt", mock_config)
        assert agent.id == "test-agent"
        assert agent.system_prompt == "Test prompt"

        # Check config file
        config_file = mock_agent_dir / "config.json"
        assert config_file.exists()
        config = json.loads(config_file.read_text())
        assert config["id"] == "test-agent"
        assert config["system_prompt"] == "Test prompt"
        assert config["provider"]["name"] == "openai"
        assert config["provider"]["model"] == "gpt-4"


def test_agent_load(mock_agent_dir: Path) -> None:
    """Test agent loading."""
    # Create config file
    config = {
        "id": "test-agent",
        "system_prompt": "Test prompt",
        "provider": {
            "name": "openai",
            "model": "gpt-4",
            "settings": {"temperature": 0.7},
        },
    }
    config_file = mock_agent_dir / "config.json"
    config_file.write_text(json.dumps(config))

    with patch("agent_foundry.agent.Path") as mock_path:
        mock_path.return_value = config_file
        with patch("agent_foundry.agent.get_provider") as mock_get_provider:
            mock_get_provider.return_value = MockProvider(
                ProviderConfig(name=ProviderType.OPENAI)
            )

            agent = Agent.load("test-agent")
            assert agent.id == "test-agent"
            assert agent.system_prompt == "Test prompt"
            assert isinstance(agent.provider, MockProvider)


def test_agent_load_not_found(mock_agent_dir: Path) -> None:
    """Test loading non-existent agent."""
    with patch("agent_foundry.agent.Path") as mock_path:
        mock_path.return_value = mock_agent_dir / "nonexistent" / "config.json"
        with pytest.raises(FileNotFoundError):
            Agent.load("nonexistent")


@pytest.mark.asyncio
async def test_agent_chat(mock_config: ProviderConfig) -> None:
    """Test agent chat functionality."""
    with patch("agent_foundry.agent.load_env_files"):
        with patch("agent_foundry.agent.get_provider") as mock_get_provider:
            mock_provider = MockProvider(mock_config)
            mock_get_provider.return_value = mock_provider

            agent = Agent("test-agent", "Test prompt", mock_config)
            chunks = []
            async for chunk in agent.chat("Hello!"):
                chunks.append(chunk)

            assert len(chunks) == 1
            assert chunks[0].content == "Mock response"
            assert chunks[0].role == AuthorRole.ASSISTANT
