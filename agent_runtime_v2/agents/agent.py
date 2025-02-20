import logging
from typing import AsyncIterator, Optional, Dict, Any, AsyncGenerator
from semantic_kernel import Kernel
from semantic_kernel.contents import ChatHistory

from ..config.types import AgentConfig
from ..conversation.context import Message, ConversationContext
from ..models.base import ModelProvider
from ..core import get_error_handler
from ..errors import AgentError, ErrorContext, RetryHandler, RetryConfig

logger = logging.getLogger(__name__)


class Agent:
    """Core agent class that manages individual agent behavior"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.id = config.id
        self.name = config.name
        self.kernel = Kernel()
        self.provider: Optional[ModelProvider] = None
        self.error_handler = get_error_handler()
        self.retry_handler = RetryHandler(
            RetryConfig(max_attempts=2, initial_delay=0.5, max_delay=5.0)
        )

    async def _handle_agent_operation(
        self, operation_name: str, **context_details
    ) -> ErrorContext:
        """Create error context for agent operations"""
        return ErrorContext(
            component="agent",
            operation=operation_name,
            details={"agent_id": self.id, "agent_name": self.name, **context_details},
        )

    def _create_agent_error(
        self,
        message: str,
        context: ErrorContext,
        cause: Exception = None,
        recovery_hint: Optional[str] = None,
    ) -> AgentError:
        """Create a standardized agent error"""
        return AgentError(
            message=message,
            context=context,
            recovery_hint=recovery_hint or "Check agent configuration and try again",
            cause=cause,
        )

    async def initialize(self) -> None:
        """Initialize the agent's resources"""
        try:
            context = await self._handle_agent_operation(
                "initialize", provider_type=self.config.model.provider
            )

            # Initialize model provider
            provider_type = self.config.model.provider
            if provider_type == "openai":
                from ..models.openai import OpenAIProvider

                self.provider = OpenAIProvider(self.config.model)
            elif provider_type == "ollama":
                from ..models.ollama import OllamaProvider

                self.provider = OllamaProvider(self.config.model)
            else:
                raise ValueError(f"Unsupported provider type: {provider_type}")

            # Initialize plugins
            await self._init_plugins()

        except Exception as e:
            raise self._create_agent_error(
                message="Failed to initialize agent",
                context=context,
                cause=e,
                recovery_hint="Check configuration and provider settings",
            ) from e

    async def _init_plugins(self) -> None:
        """Initialize agent plugins"""
        try:
            context = await self._handle_agent_operation("init_plugins")
            # TODO: Implement plugin initialization
            pass

        except Exception as e:
            raise self._create_agent_error(
                message="Failed to initialize plugins",
                context=context,
                cause=e,
                recovery_hint="Check plugin configuration",
            ) from e

    async def process_message(
        self, message: Message, context: ConversationContext
    ) -> AsyncGenerator[str, None]:
        """Process a message and generate responses"""
        try:
            operation_context = await self._handle_agent_operation(
                "process_message", message_type=message.role, context_id=context.id
            )

            if not self.provider:
                raise RuntimeError("Agent not initialized")

            # Add message to context
            await context.add_message(message)

            async def _process():
                async for chunk in self.provider.chat(context.get_history()):
                    yield chunk

            async for chunk in self.retry_handler.retry_generator(
                _process, operation_context
            ):
                yield chunk

        except Exception as e:
            logger.error(
                "Error processing message",
                extra={"error": str(e), "context": operation_context.__dict__},
            )

            if isinstance(e, AgentError):
                raise

            error = self._create_agent_error(
                message="Error processing message",
                context=operation_context,
                cause=e,
                recovery_hint="Try rephrasing your message or check agent status",
            )

            yield f"Error: {str(error)} - {error.recovery_hint}"
