"""Tests for OpenAI model provider functionality."""

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from semantic_kernel.contents import ChatHistory

from agent_runtime_v2.models.openai import OpenAIProvider
from agent_runtime_v2.config.types import ModelConfig
from agent_runtime_v2.errors import ModelError


@pytest.fixture
def openai_config():
    """Create a test OpenAI configuration."""
    return ModelConfig(
        provider="openai", model_name="gpt-4", settings={"temperature": 0.7}
    )


@pytest.mark.asyncio
async def test_openai_initialization_no_api_key(openai_config):
    """Test OpenAI provider initialization without API key."""
    with patch.dict(os.environ, clear=True):
        with pytest.raises(ModelError) as exc_info:
            OpenAIProvider(openai_config)

        assert "OpenAI API key not found" in str(exc_info.value)
        assert exc_info.value.recovery_hint == "Set OPENAI_API_KEY environment variable"


@pytest.mark.asyncio
async def test_openai_initialization_with_api_key(openai_config):
    """Test successful OpenAI provider initialization."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider(openai_config)
        assert provider.config.model_name == "gpt-4"
        assert provider.config.settings["temperature"] == 0.7


@pytest.mark.asyncio
async def test_openai_chat_completion(openai_config):
    """Test chat completion with OpenAI provider."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider(openai_config)

        # Mock the OpenAI client response
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta.content = "Hello"

        mock_response = AsyncMock()
        mock_response.__aiter__.return_value = [mock_chunk]

        provider.client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Create test history
        history = ChatHistory()
        history.add_user_message("Hi")

        # Process chat completion
        responses = []
        async for chunk in provider.chat(history):
            responses.append(chunk)

        assert responses == ["Hello"]
        provider.client.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
async def test_openai_chat_completion_api_error(openai_config):
    """Test handling of OpenAI API errors during chat completion."""
    from openai import OpenAIError as APIError

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider(openai_config)

        # Mock API error
        provider.client.chat.completions.create = AsyncMock(
            side_effect=APIError("API Error")
        )

        history = ChatHistory()
        history.add_user_message("Hi")

        responses = []
        async for chunk in provider.chat(history):
            responses.append(chunk)

        assert len(responses) == 1
        assert "OpenAI API error" in responses[0]
        assert "Check API key and model settings" in responses[0]


@pytest.mark.asyncio
async def test_openai_chat_completion_unexpected_error(openai_config):
    """Test handling of unexpected errors during chat completion."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider(openai_config)

        # Mock unexpected error
        provider.client.chat.completions.create = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        history = ChatHistory()
        history.add_user_message("Hi")

        responses = []
        async for chunk in provider.chat(history):
            responses.append(chunk)

        assert len(responses) == 1
        assert "Unexpected error" in responses[0]


@pytest.mark.asyncio
async def test_openai_embeddings(openai_config):
    """Test getting embeddings from OpenAI provider."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider(openai_config)

        # Mock embeddings response
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.1, 0.2, 0.3]

        provider.client.embeddings.create = AsyncMock(return_value=mock_response)

        embeddings = await provider.get_embeddings("test text")
        assert embeddings == [0.1, 0.2, 0.3]
        provider.client.embeddings.create.assert_called_once()


@pytest.mark.asyncio
async def test_openai_embeddings_api_error(openai_config):
    """Test handling of OpenAI API errors during embeddings generation."""
    from openai import OpenAIError as APIError

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider(openai_config)

        # Mock API error
        provider.client.embeddings.create = AsyncMock(side_effect=APIError("API Error"))

        with pytest.raises(ModelError) as exc_info:
            await provider.get_embeddings("test text")

        assert "OpenAI API error getting embeddings" in str(exc_info.value)
        assert "Check API key and model settings" in exc_info.value.recovery_hint


@pytest.mark.asyncio
async def test_openai_embeddings_unexpected_error(openai_config):
    """Test handling of unexpected errors during embeddings generation."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider(openai_config)

        # Mock unexpected error
        provider.client.embeddings.create = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        with pytest.raises(ModelError) as exc_info:
            await provider.get_embeddings("test text")

        assert "Unexpected error getting embeddings" in str(exc_info.value)


@pytest.mark.asyncio
async def test_openai_error_context(openai_config):
    """Test creation of error context in OpenAI operations."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider(openai_config)

        context = await provider._handle_api_call(
            "test_operation", model="test-model", extra_detail="test"
        )

        assert context.component == "model_provider"
        assert context.operation == "test_operation"
        assert context.details["model"] == "test-model"
        assert context.details["extra_detail"] == "test"
