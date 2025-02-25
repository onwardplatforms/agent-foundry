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
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.open_ai_prompt_execution_settings import (
    OpenAIChatPromptExecutionSettings,
)
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel import Kernel

from .base import ModelProvider
from ..config.types import ModelConfig
from ..errors import ModelError, ErrorContext, AgentRuntimeError


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
        self.client = OpenAIChatCompletion(
            ai_model_id=self.config.model,
            api_key=api_key,
        )
        self.service_id = "openai"

    async def chat(
        self, history: ChatHistory, kernel: Optional[Kernel] = None, **kwargs
    ) -> AsyncIterator[str]:
        """Process a chat message using OpenAI's streaming API.

        Args:
            history: Chat history to use for context
            kernel: Optional kernel instance for function calling
            **kwargs: Additional arguments to pass to the API

        Yields:
            Chunks of the response as they arrive

        Raises:
            ModelError: For API errors or unexpected issues
        """
        try:
            context = await self._handle_api_call(
                "chat_completion",
                model=self.config.model,
                messages=history.messages,
            )

            # Build settings dictionary from config
            settings = OpenAIChatPromptExecutionSettings(
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                top_p=self.config.top_p,
                frequency_penalty=self.config.frequency_penalty,
                presence_penalty=self.config.presence_penalty,
                function_choice_behavior=FunctionChoiceBehavior.Auto(),
            )

            # Add function definitions if kernel is provided
            if kernel:
                from ..plugins import PluginManager

                plugin_manager = PluginManager()
                plugin_manager.plugins = {
                    name: (None, plugin) for name, plugin in kernel.plugins.items()
                }
                functions = plugin_manager.get_openai_functions()
                settings.tools = functions.get("functions", [])
                settings.tool_choice = functions.get("function_call", "auto")

            try:
                async for chunk in self.client.get_streaming_chat_message_content(
                    chat_history=history,
                    settings=settings,
                    kernel=kernel,
                ):
                    if chunk.content:
                        yield chunk.content

            except Exception as e:
                raise ModelError(
                    message=f"OpenAI API error: {str(e)}",
                    context=context,
                    recovery_hint="Check API key and model settings",
                    cause=e,
                )

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
                try:
                    response = await self.client.embeddings.create(
                        model="text-embedding-ada-002", input=text
                    )
                    return response.data[0].embedding
                except Exception as e:
                    raise ModelError(
                        message=f"OpenAI API error getting embeddings: {str(e)}",
                        context=context,
                        recovery_hint="Check API key and model settings",
                        cause=e,
                    )

            try:
                return await self.retry_handler.retry(_make_request, context)
            except AgentRuntimeError as e:
                if isinstance(e.cause, ModelError):
                    raise e.cause
                raise self._create_model_error(
                    message=f"OpenAI API error getting embeddings: {str(e)}",
                    context=context,
                    cause=e,
                )

        except Exception as e:
            if isinstance(e, ModelError):
                raise
            raise self._create_model_error(
                message=f"Unexpected error getting embeddings: {str(e)}",
                context=context,
                cause=e,
            )
