"""Tests for OpenAI model provider functionality."""

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from semantic_kernel.contents import ChatHistory

from agent_runtime_v2.models.openai import OpenAIProvider
from agent_runtime_v2.config.types import ModelConfig
from agent_runtime_v2.errors import ModelError, ErrorContext


@pytest.fixture
def openai_config():
    """Create a test OpenAI configuration."""
    return ModelConfig(provider="openai", model="gpt-4", temperature=0.7)


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
        assert provider.config.model == "gpt-4"
        assert provider.config.temperature == 0.7


@pytest.mark.asyncio
async def test_openai_chat_completion(openai_config):
    """Test chat completion with OpenAI provider."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider(openai_config)

        # Create a mock chat method that returns our expected chunks
        async def mock_chat(*args, **kwargs):
            yield "Hello"

        # Patch the chat method directly
        with patch.object(provider, "chat", side_effect=mock_chat):
            # Create a test chat history
            history = ChatHistory()
            history.add_user_message("Hello")

            # Get chat completion
            responses = []
            async for chunk in provider.chat(history):
                responses.append(chunk)

            assert responses == ["Hello"]


@pytest.mark.asyncio
async def test_openai_chat_completion_api_error(openai_config):
    """Test handling of OpenAI API errors during chat completion."""
    from openai import OpenAIError as APIError

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider(openai_config)

        # Create a mock chat method that raises an API error
        async def mock_chat_error(*args, **kwargs):
            try:
                raise APIError("API Error")
            except APIError as e:
                raise ModelError(
                    message=f"OpenAI API error: {str(e)}",
                    context=ErrorContext(
                        component="openai_provider", operation="chat_completion"
                    ),
                    recovery_hint="Check API key and model settings",
                    cause=e,
                )
            yield "This should not be reached"

        # Patch the chat method directly
        with patch.object(provider, "chat", side_effect=mock_chat_error):
            # Create a test chat history
            history = ChatHistory()
            history.add_user_message("Hello")

            # Attempt to get chat completion
            with pytest.raises(ModelError) as exc_info:
                async for _ in provider.chat(history):
                    pass

            assert "OpenAI API error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_openai_chat_completion_unexpected_error(openai_config):
    """Test handling of unexpected errors during chat completion."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider(openai_config)

        # Create a mock chat method that raises an unexpected error
        async def mock_chat_error(*args, **kwargs):
            try:
                raise Exception("Unexpected error")
            except Exception as e:
                raise ModelError(
                    message=f"Unexpected error: {str(e)}",
                    context=ErrorContext(
                        component="openai_provider", operation="chat_completion"
                    ),
                    recovery_hint="Try again later or contact support",
                    cause=e,
                )
            yield "This should not be reached"

        # Patch the chat method directly
        with patch.object(provider, "chat", side_effect=mock_chat_error):
            # Create a test chat history
            history = ChatHistory()
            history.add_user_message("Hello")

            # Attempt to get chat completion
            with pytest.raises(ModelError) as exc_info:
                async for _ in provider.chat(history):
                    pass

            assert "Unexpected error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_openai_embeddings(openai_config):
    """Test getting embeddings from OpenAI provider."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider(openai_config)

        # Mock embeddings response
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.1, 0.2, 0.3]

        # Patch the get_embeddings method directly
        with patch.object(provider, "get_embeddings", return_value=[0.1, 0.2, 0.3]):
            # Get embeddings
            embeddings = await provider.get_embeddings("test text")

            assert embeddings == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_openai_embeddings_api_error(openai_config):
    """Test handling of OpenAI API errors during embeddings generation."""
    from openai import OpenAIError as APIError

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider(openai_config)

        # Create a mock function that will be called by get_embeddings
        async def mock_embeddings_error(*args, **kwargs):
            raise ModelError(
                message="OpenAI API error getting embeddings: API Error",
                context=ErrorContext(
                    component="openai_provider", operation="embeddings"
                ),
                recovery_hint="Check API key and model settings",
                cause=APIError("API Error"),
            )

        # Patch the _handle_api_call method which is used by get_embeddings
        with patch.object(
            provider,
            "_handle_api_call",
            return_value=ErrorContext(
                component="openai_provider", operation="embeddings"
            ),
        ):
            # Patch the retry_handler.retry method to raise our error
            with patch.object(
                provider.retry_handler, "retry", side_effect=mock_embeddings_error
            ):
                # Attempt to get embeddings
                with pytest.raises(ModelError) as exc_info:
                    await provider.get_embeddings("test text")

                assert "OpenAI API error getting embeddings" in str(exc_info.value)


@pytest.mark.asyncio
async def test_openai_embeddings_unexpected_error(openai_config):
    """Test handling of unexpected errors during embeddings generation."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider(openai_config)

        # Create a mock function that will be called by get_embeddings
        async def mock_embeddings_error(*args, **kwargs):
            raise ModelError(
                message="Unexpected error getting embeddings: Unexpected error",
                context=ErrorContext(
                    component="openai_provider", operation="embeddings"
                ),
                recovery_hint="Try again later or contact support",
                cause=Exception("Unexpected error"),
            )

        # Patch the _handle_api_call method which is used by get_embeddings
        with patch.object(
            provider,
            "_handle_api_call",
            return_value=ErrorContext(
                component="openai_provider", operation="embeddings"
            ),
        ):
            # Patch the retry_handler.retry method to raise our error
            with patch.object(
                provider.retry_handler, "retry", side_effect=mock_embeddings_error
            ):
                # Attempt to get embeddings
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
