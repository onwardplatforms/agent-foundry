"""
OpenAI model provider implementation.

This module provides integration with OpenAI's API, including:
- Chat completions with streaming support
- Embeddings generation
- Error handling and retries
"""

import os
from typing import AsyncIterator, Optional
from semantic_kernel.contents import ChatHistory
from openai import AsyncOpenAI, OpenAIError

from .base import ModelProvider
from ..config.types import ModelConfig
from ..errors import ModelError, ErrorContext


class OpenAIProvider(ModelProvider):
    """OpenAI implementation of the model provider.

    Provides access to OpenAI's models with:
    - Streaming chat completions
    - Embeddings generation
    - Automatic retries
    - Error handling with context
    """

    def __init__(self, config: ModelConfig):
        """Initialize the OpenAI provider.

        Args:
            config: Configuration for the provider, including model settings

        Raises:
            ModelError: If API key is not found in environment
        """
        super().__init__()
        self.config = config
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ModelError(
                message="OpenAI API key not found in environment",
                context=ErrorContext(
                    component="openai_provider", operation="initialize"
                ),
                recovery_hint="Set OPENAI_API_KEY environment variable",
            )
        self.client = AsyncOpenAI(api_key=api_key)

    async def chat(self, history: ChatHistory, **kwargs) -> AsyncIterator[str]:
        """Process a chat message using OpenAI's streaming API.

        Args:
            history: Chat history to use for context
            **kwargs: Additional arguments to pass to the API

        Yields:
            Chunks of the response as they arrive

        Raises:
            ModelError: For API errors or unexpected issues
        """
        try:
            context = await self._handle_api_call(
                "chat_completion",
                model=self.config.model_name,
                messages=history.messages,
            )

            messages = []
            for msg in history.messages:
                messages.append({"role": msg.role, "content": msg.content})

            async def _make_request():
                response = await self.client.chat.completions.create(
                    model=self.config.model_name,
                    messages=messages,
                    stream=True,
                    **self.config.settings,
                )
                async for chunk in response:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content

            async for chunk in self.retry_handler.retry_generator(
                _make_request, context
            ):
                yield chunk

        except OpenAIError as e:
            error = self._create_model_error(
                message=f"OpenAI API error: {str(e)}",
                context=context,
                cause=e,
                recovery_hint="Check API key and model settings",
            )
            yield f"Error: {str(error)} - {error.recovery_hint}"
        except Exception as e:
            error = self._create_model_error(
                message=f"Unexpected error: {str(e)}", context=context, cause=e
            )
            yield f"Error: {str(error)} - {error.recovery_hint}"

    async def get_embeddings(self, text: str) -> list[float]:
        """Get embeddings for text using OpenAI's API.

        Args:
            text: Text to get embeddings for

        Returns:
            List of embedding values

        Raises:
            ModelError: For API errors or unexpected issues
        """
        try:
            context = await self._handle_api_call(
                "embeddings", model="text-embedding-ada-002", text=text
            )

            async def _make_request():
                response = await self.client.embeddings.create(
                    model="text-embedding-ada-002", input=text
                )
                return response.data[0].embedding

            return await self.retry_handler.retry(_make_request, context)

        except OpenAIError as e:
            raise self._create_model_error(
                message=f"OpenAI API error getting embeddings: {str(e)}",
                context=context,
                cause=e,
                recovery_hint="Check API key and model settings",
            ) from e
        except Exception as e:
            raise self._create_model_error(
                message=f"Unexpected error getting embeddings: {str(e)}",
                context=context,
                cause=e,
            ) from e
