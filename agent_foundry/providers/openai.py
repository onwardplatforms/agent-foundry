"""OpenAI provider implementation."""

from typing import AsyncIterator

from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.connectors.ai.prompt_execution_settings import (
    PromptExecutionSettings,
)
from semantic_kernel.contents import ChatHistory, StreamingChatMessageContent

from agent_foundry.env import get_env_var
from agent_foundry.providers.base import OpenAISettings, Provider, ProviderConfig


class OpenAIProvider(Provider):
    """OpenAI provider implementation."""

    def __init__(self, config: ProviderConfig):
        """Initialize the OpenAI provider."""
        super().__init__(config)
        if not isinstance(self.settings, OpenAISettings):
            raise ValueError("Invalid settings type for OpenAI provider")

        # Get model from config, env, or default
        env_model = get_env_var(
            "OPENAI_MODEL",
            "",
            self.agent_id,
        )
        self.model = env_model or config.model or "gpt-3.5-turbo"

        # Initialize OpenAI client
        self.client = OpenAIChatCompletion(ai_model_id=self.model)

    async def chat(
        self, history: ChatHistory
    ) -> AsyncIterator[StreamingChatMessageContent]:
        """Process a chat message using OpenAI."""
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
