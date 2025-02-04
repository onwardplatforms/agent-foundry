"""Agent implementation for Agent Foundry."""

import json
from pathlib import Path
from typing import AsyncIterator, Optional

from semantic_kernel.contents import ChatHistory, StreamingChatMessageContent

from agent_foundry.env import load_env_files
from agent_foundry.provider_impl import Provider, get_provider
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

        # Load environment variables for this agent
        load_env_files(self.id)

        # Initialize provider
        if provider_config is None:
            provider_config = ProviderConfig(name=ProviderType.OPENAI, agent_id=self.id)
        else:
            provider_config.agent_id = self.id

        self.provider: Provider = get_provider(provider_config)

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
        # Create chat history
        history = ChatHistory()
        history.add_system_message(self.system_prompt)
        history.add_user_message(message)

        # Get response from provider
        async for chunk in self.provider.chat(history):
            yield chunk
