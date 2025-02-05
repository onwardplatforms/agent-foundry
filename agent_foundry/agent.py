"""Agent implementation for Agent Foundry."""

import json
import logging
from pathlib import Path
from typing import AsyncIterator, Optional, Union

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.ollama import OllamaChatCompletion
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.connectors.ai.prompt_execution_settings import (
    PromptExecutionSettings,
)
from semantic_kernel.contents import ChatHistory, StreamingChatMessageContent

from agent_foundry.env import load_env_files
from agent_foundry.providers import ProviderConfig, ProviderType, get_provider_config


class Agent:
    """Agent class for interacting with AI models."""

    def __init__(
        self,
        id: str,
        system_prompt: str,
        provider_config: Optional[ProviderConfig] = None,
    ):
        """Initialize the agent.

        Args:
            id: Agent ID
            system_prompt: System prompt for the agent
            provider_config: Optional provider configuration
        """
        self.id = id
        self.system_prompt = system_prompt
        self.logger = logging.getLogger("agent_foundry")

        # Initialize chat history
        self.chat_history = ChatHistory()
        self.chat_history.add_system_message(system_prompt)

        # Load environment variables for this agent
        load_env_files(self.id)

        # Initialize provider config
        if provider_config is None:
            provider_config = ProviderConfig(name=ProviderType.OPENAI, agent_id=self.id)
        else:
            provider_config.agent_id = self.id

        # Initialize kernel and chat completion service based on provider
        self.kernel = Kernel()
        self.chat_service: Union[OpenAIChatCompletion, OllamaChatCompletion]

        if provider_config.name == ProviderType.OPENAI:
            self.logger.debug(
                "Initializing OpenAI service with model: %s", provider_config.model
            )
            self.chat_service = OpenAIChatCompletion(
                ai_model_id=provider_config.model or "gpt-3.5-turbo"
            )
        elif provider_config.name == ProviderType.OLLAMA:
            self.logger.debug(
                "Initializing Ollama service with model: %s", provider_config.model
            )
            # Note: Ollama settings are handled through environment variables
            self.chat_service = OllamaChatCompletion(
                ai_model_id=provider_config.model or "llama2"
            )

        # Add chat service to kernel
        self.kernel.add_service(self.chat_service)

        # Store config for settings
        self.provider_config = provider_config

    @classmethod
    def create(
        cls,
        id: str,
        system_prompt: str,
        provider_config: Optional[ProviderConfig] = None,
    ) -> "Agent":
        """Create a new agent.

        Args:
            id: Agent ID
            system_prompt: System prompt for the agent
            provider_config: Optional provider configuration

        Returns:
            New agent instance
        """
        # Create agent directory
        agent_dir = Path(f".agents/{id}")
        agent_dir.mkdir(parents=True, exist_ok=True)

        # Create agent config
        config = {
            "id": id,
            "system_prompt": system_prompt,
            "provider": provider_config.to_dict() if provider_config else None,
        }

        # Save config
        config_path = agent_dir / "config.json"
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        return cls(id, system_prompt, provider_config)

    @classmethod
    def load(cls, id: str) -> "Agent":
        """Load an existing agent.

        Args:
            id: Agent ID

        Returns:
            Loaded agent instance

        Raises:
            FileNotFoundError: If agent does not exist
        """
        # Load agent config
        config_path = Path(f".agents/{id}/config.json")
        if not config_path.exists():
            raise FileNotFoundError(f"Agent {id} does not exist")

        with open(config_path) as f:
            config = json.load(f)

        # Get provider config
        provider_config = (
            get_provider_config(config, id) if config.get("provider") else None
        )

        return cls(
            id=config["id"],
            system_prompt=config["system_prompt"],
            provider_config=provider_config,
        )

    async def chat(self, message: str) -> AsyncIterator[StreamingChatMessageContent]:
        """Process a chat message and return the response.

        Args:
            message: User message

        Returns:
            Async generator of response chunks
        """
        self.logger.debug("Processing chat message: %s", message)

        # Add user message to history
        self.chat_history.add_user_message(message)

        # Convert provider settings to prompt execution settings
        settings = self.provider_config.get_settings()
        execution_settings = PromptExecutionSettings(
            service_id=None,
            extension_data={},
            temperature=settings.temperature,
            top_p=getattr(settings, "top_p", 1.0),
            max_tokens=getattr(settings, "max_tokens", None),
        )

        # Get response using the service
        async for chunk in self.chat_service.get_streaming_chat_message_content(
            chat_history=self.chat_history,
            settings=execution_settings,
        ):
            if chunk is not None:
                yield chunk

        # Add assistant's response to history after it's complete
        if chunk is not None:
            self.chat_history.add_assistant_message(chunk.content)
