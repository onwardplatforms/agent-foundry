"""Test provider implementations."""

import json
from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import MagicMock, patch

import pytest
import requests
from aiohttp import ClientResponse, StreamReader
from semantic_kernel.contents import AuthorRole, ChatHistory

from agent_foundry.providers import (
    OllamaSettings,
    OpenAISettings,
    ProviderConfig,
    ProviderType,
)
from agent_foundry.providers.ollama import OllamaProvider
from agent_foundry.providers.openai import OpenAIProvider


@pytest.fixture
def openai_config() -> ProviderConfig:
    """Get OpenAI provider config."""
    return ProviderConfig(
        name=ProviderType.OPENAI,
        model="gpt-3.5-turbo",
        settings={"temperature": 0.5, "top_p": 1.0, "max_tokens": 1000},
    )


@pytest.fixture
def ollama_config() -> ProviderConfig:
    """Get Ollama provider config."""
    return ProviderConfig(
        name=ProviderType.OLLAMA,
        model="llama2",
        settings={"temperature": 0.5, "base_url": "http://localhost:11434"},
    )


@pytest.fixture
def chat_history() -> ChatHistory:
    """Get chat history."""
    history = ChatHistory()
    history.add_system_message("You are a test assistant.")
    history.add_user_message("Hello!")
    return history


class TestOpenAIProvider:
    """Test OpenAI provider."""

    def test_init(self, openai_config: ProviderConfig) -> None:
        """Test provider initialization."""
        # Clear environment variables
        with patch.dict("os.environ", {}, clear=True):
            provider = OpenAIProvider(openai_config)
            assert provider.model == "gpt-3.5-turbo"
            assert isinstance(provider.settings, OpenAISettings)
            assert provider.settings.temperature == 0.5
            assert provider.settings.top_p == 1.0
            assert provider.settings.max_tokens == 1000

    def test_init_with_env(self, openai_config: ProviderConfig, tmp_path: Path) -> None:
        """Test provider initialization with environment variables."""
        # Create root .env
        root_env = tmp_path / ".env"
        root_env.write_text("OPENAI_MODEL=gpt-4\n")

        # Create agent-specific .env
        agent_dir = tmp_path / ".agents" / "test-agent"
        agent_dir.mkdir(parents=True)
        agent_env = agent_dir / ".env"
        agent_env.write_text("OPENAI_MODEL=gpt-4-turbo\n")

        with patch("agent_foundry.env.Path") as mock_path:

            def path_side_effect(path: str) -> Path:
                if path == ".env":
                    return root_env
                return tmp_path / path

            mock_path.side_effect = path_side_effect

            # No agent ID - use root .env
            provider = OpenAIProvider(openai_config)
            assert provider.model == "gpt-4"

            # With agent ID - use agent .env
            config = ProviderConfig(
                name=ProviderType.OPENAI,
                model=None,
                settings={"temperature": 0.5},
                agent_id="test-agent",
            )
            provider = OpenAIProvider(config)
            assert provider.model == "gpt-4-turbo"

    @pytest.mark.asyncio
    async def test_chat(
        self, openai_config: ProviderConfig, chat_history: ChatHistory
    ) -> None:
        """Test chat functionality."""
        provider = OpenAIProvider(openai_config)

        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.content = "Hello! I'm Claude."
        mock_response.role = "assistant"

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
            yield mock_response

        with patch(
            "semantic_kernel.connectors.ai.open_ai.OpenAIChatCompletion"
            ".get_streaming_chat_message_content",
            side_effect=mock_stream,
        ):
            chunks = []
            async for chunk in provider.chat(chat_history):
                chunks.append(chunk)

            assert len(chunks) == 1
            assert chunks[0].content == "Hello! I'm Claude."
            assert chunks[0].role == AuthorRole.ASSISTANT


class TestOllamaProvider:
    """Test Ollama provider."""

    def test_init(self, ollama_config: ProviderConfig) -> None:
        """Test provider initialization."""
        # Clear environment variables
        with patch.dict("os.environ", {}, clear=True):
            # Mock the server check
            mock_response = MagicMock()
            mock_response.json.return_value = {"version": "0.5.0"}
            with patch("requests.get", return_value=mock_response):
                provider = OllamaProvider(ollama_config)
                assert provider.model == "llama2"
                assert isinstance(provider.settings, OllamaSettings)
                assert provider.settings.temperature == 0.5
                assert provider.settings.base_url == "http://localhost:11434"

    def test_init_server_not_running(self, ollama_config: ProviderConfig) -> None:
        """Test provider initialization when server is not running."""
        with patch.dict("os.environ", {}, clear=True):
            with patch(
                "requests.get", side_effect=requests.exceptions.ConnectionError()
            ):
                with pytest.raises(RuntimeError, match="Ollama server not running"):
                    OllamaProvider(ollama_config)

    def test_init_invalid_response(self, ollama_config: ProviderConfig) -> None:
        """Test provider initialization with invalid server response."""
        with patch.dict("os.environ", {}, clear=True):
            mock_response = MagicMock()
            mock_response.json.return_value = {}
            with patch("requests.get", return_value=mock_response):
                with pytest.raises(RuntimeError, match="invalid version response"):
                    OllamaProvider(ollama_config)

    def test_init_with_env(self, ollama_config: ProviderConfig, tmp_path: Path) -> None:
        """Test provider initialization with environment variables."""
        # Create root .env
        root_env = tmp_path / ".env"
        root_env.write_text(
            "OLLAMA_MODEL=mistral\n" "OLLAMA_BASE_URL=http://test:11434\n"
        )

        # Create agent-specific .env
        agent_dir = tmp_path / ".agents" / "test-agent"
        agent_dir.mkdir(parents=True)
        agent_env = agent_dir / ".env"
        agent_env.write_text(
            "OLLAMA_MODEL=codellama\n" "OLLAMA_BASE_URL=http://agent:11434\n"
        )

        with patch("agent_foundry.env.Path") as mock_path:

            def path_side_effect(path: str) -> Path:
                if path == ".env":
                    return root_env
                return tmp_path / path

            mock_path.side_effect = path_side_effect

            # Mock the server check
            mock_response = MagicMock()
            mock_response.json.return_value = {"version": "0.5.0"}
            with patch("requests.get", return_value=mock_response):
                # No agent ID - use root .env
                provider = OllamaProvider(ollama_config)
                assert provider.model == "mistral"
                assert isinstance(provider.settings, OllamaSettings)
                assert provider.settings.base_url == "http://test:11434"

                # With agent ID - use agent .env
                config = ProviderConfig(
                    name=ProviderType.OLLAMA,
                    model=None,
                    settings={"temperature": 0.5},
                    agent_id="test-agent",
                )
                provider = OllamaProvider(config)
                assert provider.model == "codellama"
                assert isinstance(provider.settings, OllamaSettings)
                assert provider.settings.base_url == "http://agent:11434"

    @pytest.mark.asyncio
    async def test_chat(
        self, ollama_config: ProviderConfig, chat_history: ChatHistory
    ) -> None:
        """Test chat functionality."""
        with patch.dict(
            "os.environ", {"OLLAMA_BASE_URL": "http://test:11434"}, clear=True
        ):
            # Mock the server check
            mock_response = MagicMock()
            mock_response.json.return_value = {"version": "0.5.0"}
            with patch("requests.get", return_value=mock_response):
                provider = OllamaProvider(ollama_config)

                # Mock aiohttp response
                mock_response = MagicMock(spec=ClientResponse)
                mock_response.raise_for_status = MagicMock()

                # Create mock stream reader
                stream = MagicMock(spec=StreamReader)

                async def mock_iter(*args: Any, **kwargs: Any) -> AsyncIterator[bytes]:
                    yield json.dumps(
                        {"message": {"content": "Hello! I'm Llama."}}
                    ).encode() + b"\n"
                    yield b""  # EOF

                stream.__aiter__ = mock_iter
                mock_response.content = stream

                # Mock aiohttp session
                mock_session = MagicMock()
                mock_session.__aenter__.return_value = mock_session
                mock_session.post.return_value.__aenter__.return_value = mock_response

                with patch("aiohttp.ClientSession") as mock_client:
                    mock_client.return_value = mock_session

                    # Test the chat method
                    chunks = []
                    async for chunk in provider.chat(chat_history):
                        chunks.append(chunk)

                    assert len(chunks) == 1
                    assert chunks[0].content == "Hello! I'm Llama."
                    assert chunks[0].role == AuthorRole.ASSISTANT

                    # Verify API call
                    mock_session.post.assert_called_once_with(
                        "http://test:11434/api/chat",
                        json={
                            "model": "llama2",
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "You are a test assistant.",
                                },
                                {"role": "user", "content": "Hello!"},
                            ],
                            "stream": True,
                            "options": {"temperature": 0.5},
                        },
                        headers={"Content-Type": "application/json"},
                    )

    @pytest.mark.asyncio
    async def test_chat_error_handling(
        self, ollama_config: ProviderConfig, chat_history: ChatHistory
    ) -> None:
        """Test chat error handling."""
        # Mock the server check
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": "0.5.0"}
        with patch("requests.get", return_value=mock_response):
            provider = OllamaProvider(ollama_config)

            # Mock aiohttp response
            mock_response = MagicMock(spec=ClientResponse)
            mock_response.raise_for_status = MagicMock()

            # Create mock stream reader
            stream = MagicMock(spec=StreamReader)

            async def mock_iter(*args: Any, **kwargs: Any) -> AsyncIterator[bytes]:
                yield json.dumps({"error": "Something went wrong"}).encode() + b"\n"
                yield b""  # EOF

            stream.__aiter__ = mock_iter
            mock_response.content = stream

            # Mock aiohttp session
            mock_session = MagicMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.post.return_value.__aenter__.return_value = mock_response

            with patch("aiohttp.ClientSession") as mock_client:
                mock_client.return_value = mock_session

                # Test error handling
                with pytest.raises(
                    RuntimeError, match="Ollama error: Something went wrong"
                ):
                    async for _ in provider.chat(chat_history):
                        pass
