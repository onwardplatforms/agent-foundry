from typing import Dict, List, AsyncIterator, Optional, Any, AsyncGenerator
from .context import ConversationContext, Message
from ..agents.agent import Agent
from ..config.types import ConversationConfig
from semantic_kernel.contents import ChatHistory

from ..core import get_error_handler
from ..errors import (
    ConversationError,
    ErrorContext,
    RetryHandler,
    RetryConfig,
    AgentError,
)


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
        context: Optional[ErrorContext] = None,
        cause: Exception = None,
        recovery_hint: Optional[str] = None,
    ) -> ConversationError:
        """Create a standardized conversation error"""
        if isinstance(cause, (ValueError, AgentError)):
            message = str(cause)
        return ConversationError(
            message=message,
            context=context,
            recovery_hint=recovery_hint or "Try starting a new conversation",
            cause=cause,
        )

    async def add_message(self, role: str, content: str) -> None:
        """Add a message to conversation with error handling"""
        context = None
        try:
            context = await self._handle_conversation(
                "add_message", role=role, content_length=len(content)
            )

            if role == "user":
                self.history.messages.append(Message(content=content, role=role))
            elif role == "assistant":
                self.history.messages.append(Message(content=content, role=role))
            elif role == "system":
                self.history.messages.append(Message(content=content, role=role))

            # Apply memory window if configured
            if self.config.get("memory_window"):
                window = self.config["memory_window"]
                if len(self.history.messages) > window:
                    self.history.messages = self.history.messages[-window:]

        except Exception as e:
            raise self._create_conversation_error(
                message="Failed to add message", context=context, cause=e
            ) from e

    async def process_message(self, message: str) -> str:
        """Process a message in conversation with error handling"""
        context = None
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
        context = None
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
        context = None
        try:
            context = await self._handle_conversation(
                "create_conversation", conversation_id=config.id, num_agents=len(agents)
            )

            # Create conversation context
            conv_context = ConversationContext(config.id)
            self.conversations[config.id] = conv_context

            # Store agents for this conversation
            self.agents[config.id] = {agent.id: agent for agent in agents}

            # Store conversation configuration in metadata
            conv_context.metadata.update(
                {
                    "memory_enabled": config.memory_enabled,
                    "memory_window": config.memory_window,
                    "turn_strategy": config.turn_strategy,
                    "current_agent_idx": 0,  # Initialize agent index for turn taking
                    "agent_order": [agent.id for agent in agents],  # Store agent order
                }
            )

            return conv_context

        except Exception as e:
            raise self._create_conversation_error(
                message="Failed to create conversation",
                context=context,
                cause=e,
                recovery_hint="Try creating a new conversation with different settings",
            ) from e

    async def _process_agent_response(self, response: Any) -> AsyncIterator[str]:
        """Process an agent's response and yield chunks"""
        try:
            if isinstance(response, (AsyncGenerator, AsyncIterator)):
                async for chunk in response:
                    yield chunk
            elif hasattr(response, "__aiter__"):
                async for chunk in response:
                    yield chunk
            elif hasattr(response, "__iter__"):
                for chunk in response:
                    yield str(chunk)
            else:
                yield str(response)
        except Exception as e:
            if isinstance(e, AgentError):
                raise e
            raise

    async def process_message_in_conversation(
        self, conversation_id: str, message: Message
    ) -> AsyncIterator[str]:
        """Process a message in a conversation"""
        context = None
        try:
            context = await self._handle_conversation(
                "process_message_in_conversation", conversation_id=conversation_id
            )

            # Get conversation context
            conv_context = self.conversations.get(conversation_id)
            if not conv_context:
                raise ValueError(f"Conversation {conversation_id} not found")

            # Get agents for this conversation
            agents = self.agents.get(conversation_id, {})
            if not agents:
                raise ValueError(f"No agents found for conversation {conversation_id}")

            # Add message to conversation history
            await conv_context.add_message(message)

            # Get turn strategy and agent order from metadata
            turn_strategy = conv_context.metadata.get("turn_strategy", "round_robin")
            agent_order = conv_context.metadata.get("agent_order", [])
            if not agent_order:
                # Sort agents by their ID to ensure consistent order
                agent_order = sorted(agents.keys())
                conv_context.metadata["agent_order"] = agent_order

            # For the first message, let all agents respond
            if len(conv_context.history.messages) == 1:
                for agent_id in agent_order:
                    agent = agents[agent_id]
                    try:
                        response = agent.process_message(message, conv_context)
                        if hasattr(response, "__aiter__"):  # Handle async generators
                            async for chunk in response:
                                yield chunk
                        else:
                            # For non-generator responses, we need to await them
                            result = await response
                            yield result
                    except Exception as e:
                        if isinstance(e, AgentError):
                            raise e
                        raise self._create_conversation_error(
                            message=str(e),
                            context=context,
                            cause=e,
                            recovery_hint="Try rephrasing your message or using a different agent",
                        ) from e
                # Initialize current_agent_idx for future turns
                conv_context.metadata["current_agent_idx"] = 0
            else:
                if turn_strategy == "round_robin":
                    # Get current agent index
                    current_idx = conv_context.metadata.get("current_agent_idx", 0)

                    # Process with all agents in sequence starting from current_idx
                    for i in range(len(agent_order)):
                        idx = (current_idx + i) % len(agent_order)
                        agent = agents[agent_order[idx]]
                        try:
                            response = agent.process_message(message, conv_context)
                            if hasattr(
                                response, "__aiter__"
                            ):  # Handle async generators
                                async for chunk in response:
                                    yield chunk
                            else:
                                # For non-generator responses, we need to await them
                                result = await response
                                yield result
                        except Exception as e:
                            if isinstance(e, AgentError):
                                raise e
                            raise self._create_conversation_error(
                                message=str(e),
                                context=context,
                                cause=e,
                                recovery_hint="Try rephrasing your message or using a different agent",
                            ) from e

                    # Update agent index for next turn
                    conv_context.metadata["current_agent_idx"] = (
                        current_idx + len(agent_order)
                    ) % len(agent_order)
                else:
                    # Process with all agents in sequence
                    for agent_id in agent_order:
                        agent = agents[agent_id]
                        try:
                            response = agent.process_message(message, conv_context)
                            if hasattr(
                                response, "__aiter__"
                            ):  # Handle async generators
                                async for chunk in response:
                                    yield chunk
                            else:
                                # For non-generator responses, we need to await them
                                result = await response
                                yield result
                        except Exception as e:
                            if isinstance(e, AgentError):
                                raise e
                            raise self._create_conversation_error(
                                message=str(e),
                                context=context,
                                cause=e,
                                recovery_hint="Try rephrasing your message or using a different agent",
                            ) from e

        except Exception as e:
            if isinstance(e, (ConversationError, AgentError)):
                raise
            raise self._create_conversation_error(
                message="Error processing message in conversation",
                context=context,
                cause=e,
            ) from e

    def get_conversation(self, conversation_id: str) -> ConversationContext:
        """Get a conversation context by ID"""
        context = self.conversations.get(conversation_id)
        if not context:
            raise ValueError(f"Conversation {conversation_id} not found")
        return context
