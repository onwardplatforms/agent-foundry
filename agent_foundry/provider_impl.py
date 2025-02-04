"""Provider implementations for Agent Foundry."""

import json
from abc import ABC, abstractmethod
from typing import AsyncIterator

import aiohttp
import requests
from requests.exceptions import RequestException
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
from agent_foundry.providers import (
    OllamaSettings,
    OpenAISettings,
    ProviderConfig,
    ProviderSettings,
)


class Provider(ABC):
    """Base class for providers."""

    def __init__(self, config: ProviderConfig):
        """Initialize the provider.

        Args:
            config: Provider configuration
        """
        self.config = config
        self.settings: ProviderSettings = config.get_settings()
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
        if not isinstance(self.settings, OpenAISettings):
            raise ValueError("Invalid settings type for OpenAI provider")

        # Get model from config, env, or default
        if self.agent_id:
            # Use agent-specific environment variable if agent_id is set
            env_model = get_env_var(
                "AGENT_FOUNDRY_OPENAI_MODEL",
                "",
                self.agent_id,
            )
            self.model = env_model or config.model or "gpt-3.5-turbo"
        else:
            # Use global environment variable if no agent_id
            env_model = get_env_var(
                "OPENAI_MODEL",
                "",
                None,
            )
            self.model = env_model or config.model or "gpt-3.5-turbo"

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
        if not isinstance(self.settings, OpenAISettings):
            raise ValueError("Invalid settings type for OpenAI provider")

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

    def __init__(self, config: ProviderConfig) -> None:
        """Initialize provider.

        Args:
            config: Provider configuration

        Raises:
            RuntimeError: If Ollama server is not running or not accessible
        """
        # Get model and base URL from environment variables first
        if config.agent_id:
            # Use agent-specific environment variables if agent_id is set
            env_model = get_env_var(
                "AGENT_FOUNDRY_OLLAMA_MODEL",
                "",
                config.agent_id,
            )
            env_base_url = get_env_var(
                "AGENT_FOUNDRY_OLLAMA_BASE_URL",
                "",
                config.agent_id,
            )
        else:
            # Use global environment variables if no agent_id
            env_model = get_env_var(
                "OLLAMA_MODEL",
                "",
                None,
            )
            env_base_url = get_env_var(
                "OLLAMA_BASE_URL",
                "",
                None,
            )

        # Set model from environment or config or default
        self.model = env_model or config.model or "llama2"

        # Update settings with environment values
        settings = config.settings or {}
        settings["base_url"] = (
            env_base_url or settings.get("base_url") or "http://localhost:11434"
        )

        # Create a new config with updated settings
        updated_config = ProviderConfig(
            name=config.name,
            model=config.model,
            settings=settings,
            agent_id=config.agent_id,
        )

        super().__init__(updated_config)
        if not isinstance(self.settings, OllamaSettings):
            raise ValueError("Invalid settings type for Ollama provider")

        # Check if Ollama server is running
        self._check_server()

    def _check_server(self) -> None:
        """Check if Ollama server is running.

        Raises:
            RuntimeError: If Ollama server is not running or not accessible
        """
        if not isinstance(self.settings, OllamaSettings):
            raise ValueError("Invalid settings type for Ollama provider")

        try:
            response = requests.get(f"{self.settings.base_url}/api/version")
            response.raise_for_status()
            version = response.json().get("version")
            if not version:
                raise RuntimeError("Ollama server returned invalid version response")
        except RequestException as e:
            raise RuntimeError(
                f"Ollama server not running at {self.settings.base_url}: {str(e)}"
            ) from e

    async def chat(
        self, history: ChatHistory
    ) -> AsyncIterator[StreamingChatMessageContent]:
        """Process a chat message using Ollama.

        Args:
            history: Chat history

        Returns:
            Async generator of response chunks

        Raises:
            RuntimeError: If Ollama returns an error
        """
        if not isinstance(self.settings, OllamaSettings):
            raise ValueError("Invalid settings type for Ollama provider")

        messages = []
        for msg in history.messages:
            if msg.role == AuthorRole.SYSTEM:
                messages.append({"role": "system", "content": msg.content})
            elif msg.role == AuthorRole.USER:
                messages.append({"role": "user", "content": msg.content})
            elif msg.role == AuthorRole.ASSISTANT:
                messages.append({"role": "assistant", "content": msg.content})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": self.settings.temperature},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.settings.base_url}/api/chat",
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                response.raise_for_status()
                async for line in response.content:
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if "error" in data:
                            raise RuntimeError(f"Ollama error: {data['error']}")
                        if "message" in data:
                            yield StreamingChatMessageContent(
                                role=AuthorRole.ASSISTANT,
                                content=data["message"]["content"],
                                choice_index=0,
                            )
                    except json.JSONDecodeError:
                        continue


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
