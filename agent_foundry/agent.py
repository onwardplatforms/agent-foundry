"""Base agent implementation for Agent Foundry."""

from pathlib import Path
from typing import Optional

from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.connectors.ai.prompt_execution_settings import (
    PromptExecutionSettings,
)
from semantic_kernel.contents import ChatHistory, StreamingChatMessageContent

from agent_foundry.constants import AGENTS_DIR, DEFAULT_MODEL, DEFAULT_SYSTEM_PROMPT


class Agent:
    """Base agent class for chat interactions."""

    def __init__(
        self,
        agent_id: str,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        model: str = DEFAULT_MODEL,
        agent_dir: Optional[Path] = None,
    ) -> None:
        """Initialize the agent.

        Args:
            agent_id: Unique identifier for the agent
            system_prompt: The system message that defines the agent's personality
            model: The model to use for chat completion
            agent_dir: Directory where agent files are stored
        """
        self.agent_id = agent_id
        self.model = model
        self.agent_dir = agent_dir or Path(AGENTS_DIR) / agent_id
        self._system_prompt = system_prompt
        self.chat_history = ChatHistory(system_message=system_prompt)
        self.chat_service = OpenAIChatCompletion(
            ai_model_id=model,
        )

    @property
    def system_prompt(self) -> str:
        """Get the system prompt for this agent."""
        return self._system_prompt

    async def chat(self, message: str) -> str:
        """Process a chat message and return the response.

        Args:
            message: The user's message

        Returns:
            The agent's response
        """
        self.chat_history.add_user_message(message)

        settings = PromptExecutionSettings(
            service_id=None,  # Use default service
            extension_data={},  # No additional data needed
            temperature=0.7,  # Standard temperature for balanced responses
            top_p=0.95,  # Standard top_p for good diversity
            max_tokens=1000,  # Reasonable limit for responses
        )

        response = self.chat_service.get_streaming_chat_message_content(
            chat_history=self.chat_history,
            settings=settings,
        )

        # Capture the chunks of the response and print them as they arrive
        chunks: list[StreamingChatMessageContent] = []
        async for chunk in response:
            if chunk:
                chunks.append(chunk)
                print(chunk, end="", flush=True)  # Print each chunk immediately

        # Combine the chunks into a single message
        full_message = sum(chunks[1:], chunks[0])
        self.chat_history.add_message(full_message)

        return str(full_message)

    @classmethod
    def create(cls, agent_id: str, system_prompt: Optional[str] = None) -> "Agent":
        """Create a new agent with default settings.

        Args:
            agent_id: Unique identifier for the agent
            system_prompt: Optional system prompt, uses default if not provided

        Returns:
            A new Agent instance
        """
        return cls(
            agent_id=agent_id,
            system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
        )
