from typing import Dict, List, AsyncIterator, Optional, Any
from .context import ConversationContext, Message
from ..agents.agent import Agent
from ..config.types import ConversationConfig
from semantic_kernel.contents import ChatHistory

from ..core import get_error_handler
from ..errors import ConversationError, ErrorContext, RetryHandler, RetryConfig


class ConversationManager:
    """Manages conversations with error handling"""

    def __init__(self, agent: Agent, config: Optional[Dict[str, Any]] = None):
        self.agent = agent
        self.config = config or {}
        self.error_handler = get_error_handler()
        self.retry_handler = RetryHandler(
            RetryConfig(max_attempts=2, initial_delay=0.5, max_delay=5.0)
        )
        self.history = ChatHistory()
        self.conversations: Dict[str, ConversationContext] = {}
        self.agents: Dict[str, Dict[str, Agent]] = {}  # conv_id -> {agent_id -> agent}

    async def _handle_conversation(
        self, operation_name: str, **context_details
    ) -> ErrorContext:
        """Create error context for conversation operations"""
        return ErrorContext(
            component="conversation",
            operation=operation_name,
            details={"history_length": len(self.history.messages), **context_details},
        )

    def _create_conversation_error(
        self,
        message: str,
        context: ErrorContext,
        cause: Exception = None,
        recovery_hint: Optional[str] = None,
    ) -> ConversationError:
        """Create a standardized conversation error"""
        return ConversationError(
            message=message,
            context=context,
            recovery_hint=recovery_hint or "Try starting a new conversation",
            cause=cause,
        )

    async def add_message(self, role: str, content: str) -> None:
        """Add a message to conversation with error handling"""
        try:
            context = await self._handle_conversation(
                "add_message", role=role, content_length=len(content)
            )

            if role == "user":
                self.history.add_user_message(content)
            elif role == "assistant":
                self.history.add_assistant_message(content)
            elif role == "system":
                self.history.add_system_message(content)

        except Exception as e:
            raise self._create_conversation_error(
                message="Failed to add message", context=context, cause=e
            ) from e

    async def process_message(self, message: str) -> str:
        """Process a message in conversation with error handling"""
        try:
            context = await self._handle_conversation(
                "process_message", message_length=len(message)
            )

            # Add user message
            await self.add_message("user", message)

            # Get agent response
            response = await self.agent.process_message(self.history)

            # Add agent response
            await self.add_message("assistant", response)

            return response

        except Exception as e:
            # Let agent errors propagate up
            if isinstance(e, ConversationError):
                raise

            raise self._create_conversation_error(
                message="Error processing conversation message",
                context=context,
                cause=e,
                recovery_hint="Try rephrasing your message or starting a new conversation",
            ) from e

    async def clear_history(self) -> None:
        """Clear conversation history with error handling"""
        try:
            context = await self._handle_conversation("clear_history")
            self.history = ChatHistory()

        except Exception as e:
            raise self._create_conversation_error(
                message="Failed to clear conversation history", context=context, cause=e
            ) from e

    async def create_conversation(
        self, config: ConversationConfig, agents: List[Agent]
    ) -> ConversationContext:
        """Create a new conversation with the specified agents"""
        # Create conversation context
        context = ConversationContext(config.id)
        self.conversations[config.id] = context

        # Store agents for this conversation
        self.agents[config.id] = {agent.id: agent for agent in agents}

        return context

    async def process_message_in_conversation(
        self, conversation_id: str, message: Message
    ) -> AsyncIterator[str]:
        """Process a message in a conversation"""
        # Get conversation context
        context = self.conversations.get(conversation_id)
        if not context:
            raise ValueError(f"Conversation {conversation_id} not found")

        # Get agents for this conversation
        agents = self.agents.get(conversation_id, {})
        if not agents:
            raise ValueError(f"No agents found for conversation {conversation_id}")

        # For now, just process with all agents in sequence
        # TODO: Implement proper turn taking strategies
        for agent in agents.values():
            async for response in agent.process_message(message, context):
                yield response

    def get_conversation(self, conversation_id: str) -> ConversationContext:
        """Get a conversation context by ID"""
        context = self.conversations.get(conversation_id)
        if not context:
            raise ValueError(f"Conversation {conversation_id} not found")
        return context
