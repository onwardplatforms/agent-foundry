"""Tests for Agent class."""

import json
from pathlib import Path
from typing import Generator
from unittest.mock import create_autospec, patch

import pytest
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.contents import AuthorRole, StreamingChatMessageContent

from agent_foundry.agent import Agent
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


def test_agent_init(mock_config: ProviderConfig) -> None:
    """Test agent initialization."""
    with patch("agent_foundry.agent.load_env_files") as mock_load_env:
        with patch("agent_foundry.agent.OpenAIChatCompletion") as mock_service_class:
            # Create a properly typed mock service
            mock_service = create_autospec(OpenAIChatCompletion)
            mock_service.service_id = "openai-chat"
            mock_service_class.return_value = mock_service

            agent = Agent("test-agent", "Test prompt", mock_config)
            assert agent.id == "test-agent"
            assert agent.system_prompt == "Test prompt"
            assert isinstance(agent.chat_service, OpenAIChatCompletion)

            mock_load_env.assert_called_once_with("test-agent")
            mock_service_class.assert_called_once_with(ai_model_id="gpt-4")


def test_agent_init_default_provider() -> None:
    """Test agent initialization with default provider."""
    with patch("agent_foundry.agent.load_env_files"):
        with patch("agent_foundry.agent.OpenAIChatCompletion") as mock_service_class:
            # Create a properly typed mock service
            mock_service = create_autospec(OpenAIChatCompletion)
            mock_service.service_id = "openai-chat"
            mock_service_class.return_value = mock_service

            agent = Agent("test-agent", "Test prompt")
            assert isinstance(agent.chat_service, OpenAIChatCompletion)
            mock_service_class.assert_called_once_with(ai_model_id="gpt-3.5-turbo")


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
        with patch("agent_foundry.agent.OpenAIChatCompletion") as mock_service_class:
            # Create a properly typed mock service
            mock_service = create_autospec(OpenAIChatCompletion)
            mock_service.service_id = "openai-chat"
            mock_service_class.return_value = mock_service

            agent = Agent.load("test-agent")
            assert agent.id == "test-agent"
            assert agent.system_prompt == "Test prompt"
            mock_service_class.assert_called_once_with(ai_model_id="gpt-4")


def test_agent_load_not_found() -> None:
    """Test agent loading when agent does not exist."""
    with pytest.raises(FileNotFoundError):
        Agent.load("nonexistent-agent")


@pytest.mark.asyncio
async def test_agent_chat(mock_config: ProviderConfig) -> None:
    """Test agent chat functionality."""
    with patch("agent_foundry.agent.load_env_files"):
        with patch("agent_foundry.agent.OpenAIChatCompletion") as mock_service_class:
            # Create a properly typed mock service
            mock_service = create_autospec(OpenAIChatCompletion, instance=True)
            mock_service.service_id = "openai-chat"
            mock_service_class.return_value = mock_service

            # Set up the mock response
            mock_response = StreamingChatMessageContent(
                role=AuthorRole.ASSISTANT,
                content="Mock response",
                choice_index=0,
            )

            # Create an async iterator for the response
            async def mock_stream():
                yield mock_response

            # Set up the mock to return our async iterator
            mock_service.get_streaming_chat_message_content.return_value = mock_stream()

            # Create agent and test chat
            agent = Agent("test-agent", "Test prompt", mock_config)
            response = [chunk async for chunk in agent.chat("Hello")]
            assert len(response) == 1
            assert response[0].content == "Mock response"

            # Verify the service was called correctly
            assert mock_service.get_streaming_chat_message_content.called


@pytest.mark.asyncio
async def test_chat_history_initialization(mock_config: ProviderConfig) -> None:
    """Test that chat history is initialized with system prompt."""
    with patch("agent_foundry.agent.load_env_files"):
        with patch("agent_foundry.agent.OpenAIChatCompletion") as mock_service_class:
            # Create a properly typed mock service
            mock_service = create_autospec(OpenAIChatCompletion)
            mock_service.service_id = "openai-chat"
            mock_service_class.return_value = mock_service

            agent = Agent("test-agent", "Test system prompt", mock_config)

            # Verify chat history is initialized with system prompt
            assert len(agent.chat_history.messages) == 1
            assert agent.chat_history.messages[0].role == AuthorRole.SYSTEM
            assert agent.chat_history.messages[0].content == "Test system prompt"


@pytest.mark.asyncio
async def test_chat_history_persistence(mock_config: ProviderConfig) -> None:
    """Test that chat history persists between messages."""
    with patch("agent_foundry.agent.load_env_files"):
        with patch("agent_foundry.agent.OpenAIChatCompletion") as mock_service_class:
            # Create a properly typed mock service
            mock_service = create_autospec(OpenAIChatCompletion)
            mock_service.service_id = "openai-chat"
            mock_service_class.return_value = mock_service

            # Set up mock responses
            responses = [
                StreamingChatMessageContent(
                    role=AuthorRole.ASSISTANT,
                    content="First response",
                    choice_index=0,
                ),
                StreamingChatMessageContent(
                    role=AuthorRole.ASSISTANT,
                    content="Second response",
                    choice_index=0,
                ),
            ]

            response_index = 0

            async def mock_stream():
                nonlocal response_index
                yield responses[response_index]
                response_index += 1

            mock_service.get_streaming_chat_message_content.side_effect = [
                mock_stream(),
                mock_stream(),
            ]

            # Create agent and test chat
            agent = Agent("test-agent", "Test system prompt", mock_config)

            # First message
            response1 = [chunk async for chunk in agent.chat("First message")]
            assert len(response1) == 1
            assert response1[0].content == "First response"

            # Verify chat history after first message
            assert len(agent.chat_history.messages) == 3  # system + user + assistant
            assert agent.chat_history.messages[0].role == AuthorRole.SYSTEM
            assert agent.chat_history.messages[0].content == "Test system prompt"
            assert agent.chat_history.messages[1].role == AuthorRole.USER
            assert agent.chat_history.messages[1].content == "First message"
            assert agent.chat_history.messages[2].role == AuthorRole.ASSISTANT
            assert agent.chat_history.messages[2].content == "First response"

            # Second message
            response2 = [chunk async for chunk in agent.chat("Second message")]
            assert len(response2) == 1
            assert response2[0].content == "Second response"

            # Verify chat history after second message
            assert (
                len(agent.chat_history.messages) == 5
            )  # system + user1 + assistant1 + user2 + assistant2
            assert agent.chat_history.messages[3].role == AuthorRole.USER
            assert agent.chat_history.messages[3].content == "Second message"
            assert agent.chat_history.messages[4].role == AuthorRole.ASSISTANT
            assert agent.chat_history.messages[4].content == "Second response"
