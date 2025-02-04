"""Provider implementations for Agent Foundry."""

import json
from abc import ABC, abstractmethod
from typing import AsyncIterator

import aiohttp
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.connectors.ai.prompt_execution_settings import (
    PromptExecutionSettings,
)
from semantic_kernel.contents import (
    AuthorRole,
    ChatHistory,
    StreamingChatMessageContent,
)

from agent_foundry.env import get_env_var
from agent_foundry.providers import OllamaSettings, OpenAISettings, ProviderConfig


class Provider(ABC):
    """Base class for providers."""

    def __init__(self, config: ProviderConfig):
        """Initialize the provider.

        Args:
            config: Provider configuration
        """
        self.config = config
        self.settings = config.get_settings()
        self.agent_id = getattr(config, "agent_id", None)

    @abstractmethod
    def chat(self, history: ChatHistory) -> AsyncIterator[StreamingChatMessageContent]:
        """Process a chat message and return the response.

        Args:
            history: Chat history

        Returns:
            Async generator of response chunks
        """
        raise NotImplementedError  # pragma: no cover


class OpenAIProvider(Provider):
    """OpenAI provider implementation."""

    def __init__(self, config: ProviderConfig):
        """Initialize the OpenAI provider.

        Args:
            config: Provider configuration
        """
        super().__init__(config)
        self.settings: OpenAISettings

        # Get model from config, env, or default
        self.model = config.model or get_env_var(
            "OPENAI_MODEL", "gpt-3.5-turbo", self.agent_id
        )

        # Initialize OpenAI client
        self.client = OpenAIChatCompletion(ai_model_id=self.model)

    async def chat(
        self, history: ChatHistory
    ) -> AsyncIterator[StreamingChatMessageContent]:
        """Process a chat message using OpenAI.

        Args:
            history: Chat history

        Returns:
            Async generator of response chunks
        """
        settings = PromptExecutionSettings(
            service_id=None,
            extension_data={},
            temperature=self.settings.temperature,
            top_p=self.settings.top_p,
            max_tokens=self.settings.max_tokens,
        )

        async for chunk in self.client.get_streaming_chat_message_content(
            chat_history=history,
            settings=settings,
        ):
            if chunk is not None:
                yield chunk


class OllamaProvider(Provider):
    """Ollama provider implementation."""

    def __init__(self, config: ProviderConfig):
        """Initialize the Ollama provider.

        Args:
            config: Provider configuration
        """
        super().__init__(config)
        self.settings: OllamaSettings

        # Get model and host from config, env, or default
        self.model = config.model or get_env_var(
            "OLLAMA_MODEL", "llama2", self.agent_id
        )
        self.base_url = self.settings.base_url or get_env_var(
            "OLLAMA_HOST", "http://localhost:11434", self.agent_id
        )

    async def chat(
        self, history: ChatHistory
    ) -> AsyncIterator[StreamingChatMessageContent]:
        """Process a chat message using Ollama.

        Args:
            history: Chat history

        Returns:
            Async generator of response chunks
        """
        # Convert chat history to Ollama format
        messages = []
        for message in history.messages:
            messages.append(
                {
                    "role": message.role.lower(),
                    "content": message.content,
                }
            )

        # Prepare request payload
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self.settings.temperature,
            },
        }

        # Make streaming request to Ollama API
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                response.raise_for_status()

                # Process streaming response
                async for line in response.content:
                    if not line:
                        continue

                    try:
                        chunk_data = json.loads(line)
                        if "error" in chunk_data:
                            raise RuntimeError(f"Ollama error: {chunk_data['error']}")

                        if "message" in chunk_data:
                            content = chunk_data["message"].get("content", "")
                            if content:
                                yield StreamingChatMessageContent(
                                    role=AuthorRole.ASSISTANT,
                                    content=content,
                                    choice_index=0,  # Ollama only returns one choice
                                )
                    except json.JSONDecodeError:
                        continue  # Skip invalid JSON lines


def get_provider(config: ProviderConfig) -> Provider:
    """Get the appropriate provider instance.

    Args:
        config: Provider configuration

    Returns:
        Provider instance

    Raises:
        ValueError: If provider type is unknown
    """
    if config.name == "openai":
        return OpenAIProvider(config)
    elif config.name == "ollama":
        return OllamaProvider(config)
    else:
        raise ValueError(f"Unknown provider type: {config.name}")
