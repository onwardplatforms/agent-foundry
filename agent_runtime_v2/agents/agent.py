import logging
from typing import AsyncIterator, Optional, Dict, Any, AsyncGenerator
from semantic_kernel import Kernel
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.utils.author_role import AuthorRole
from semantic_kernel.contents.streaming_chat_message_content import (
    StreamingChatMessageContent,
)
from semantic_kernel.contents.function_call_content import FunctionCallContent
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.exceptions.content_exceptions import ContentAdditionException

from ..config.types import AgentConfig
from ..conversation.context import Message, ConversationContext
from ..models.base import ModelProvider
from ..core import get_error_handler
from ..errors import AgentError, ErrorContext, RetryHandler, RetryConfig
from ..utils.logging import configure_logging, LogLevel

logger = logging.getLogger(__name__)


class Agent:
    """Core agent class that manages individual agent behavior"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.id = config.id
        self.name = config.name

        # Configure logging based on agent configuration
        # This will only affect loggers used by this agent instance
        agent_logger = logging.getLogger(f"agent.{self.id}")
        agent_logger.setLevel(config.log_level)
        logger.debug(f"Agent logger configured with level: {config.log_level}")

        self.kernel = Kernel()
        self.provider: Optional[ModelProvider] = None
        self.error_handler = get_error_handler()
        self.retry_handler = RetryHandler(
            RetryConfig(max_attempts=2, initial_delay=0.5, max_delay=5.0)
        )
        logger.info(f"Agent initialized with config: id={self.id}, name={self.name}")

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
            logger.debug("Initializing agent with context: %s", context)

            # Initialize model provider
            provider_type = self.config.model.provider
            logger.info("Initializing model provider: %s", provider_type)
            if provider_type == "openai":
                from ..models.openai import OpenAIProvider

                self.provider = OpenAIProvider(self.config.model)
                # Register the provider with the kernel
                self.kernel.add_service(self.provider.client, "openai")
                logger.info(
                    f"OpenAI provider initialized with model: {self.config.model.model}"
                )
            elif provider_type == "ollama":
                from ..models.ollama import OllamaProvider

                self.provider = OllamaProvider(self.config.model)
                # Register the provider with the kernel
                self.kernel.add_service(self.provider.client, "ollama")
                logger.info(
                    f"Ollama provider initialized with model: {self.config.model.model}"
                )
            else:
                raise ValueError(f"Unsupported provider type: {provider_type}")
            logger.debug("Model provider initialized: %s", self.provider)

            # Initialize plugins
            await self._init_plugins()
            logger.info("Agent initialization complete")

        except Exception as e:
            logger.error("Failed to initialize agent", exc_info=e)
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
            logger.debug("Initializing plugins with context: %s", context)

            # Initialize plugin manager
            from ..plugins import PluginManager

            self.plugin_manager = PluginManager()
            logger.debug("Plugin manager created")

            # Load configured plugins
            logger.info(f"Loading {len(self.config.plugins)} plugins")
            for i, plugin_config in enumerate(self.config.plugins):
                logger.debug(
                    f"Loading plugin {i+1}/{len(self.config.plugins)} with config: {plugin_config}"
                )
                try:
                    logger.debug(f"Plugin source: {plugin_config.source}")
                    logger.debug(f"Plugin variables: {plugin_config.variables}")
                    plugin_instance = await self.plugin_manager.load_plugin(
                        plugin_config.source, plugin_config.variables or {}
                    )

                    # Log plugin details
                    logger.info(
                        f"Plugin loaded: name={plugin_instance.name}, class={plugin_instance.__class__.__name__}"
                    )
                    logger.debug(f"Plugin description: {plugin_instance.description}")
                    logger.debug(
                        f"Plugin instructions: {plugin_instance.plugin_instructions}"
                    )

                    # Register plugin with the kernel
                    logger.debug(
                        f"Registering plugin {plugin_instance.name} with kernel"
                    )
                    self.kernel.add_plugin(plugin_instance, plugin_instance.name)
                    logger.info(f"Plugin {plugin_instance.name} registered with kernel")

                    # Log available functions
                    kernel_functions = plugin_instance.__class__.get_kernel_functions()
                    logger.debug(
                        f"Plugin {plugin_instance.name} has {len(kernel_functions)} kernel functions: {list(kernel_functions.keys())}"
                    )
                except Exception as e:
                    logger.error(f"Error loading plugin: {e}", exc_info=e)
                    raise

                logger.debug(
                    f"Plugin {i+1}/{len(self.config.plugins)} loaded and registered successfully"
                )

            # Add chat function to kernel
            logger.debug("Adding chat function to kernel")
            self.kernel.add_function(
                prompt="{{$chat_history}}{{$user_input}}",
                plugin_name="ChatBot",
                function_name="Chat",
            )
            logger.debug("Added chat function to kernel")

            # Log all registered plugins in kernel at debug level only
            logger.debug(f"Kernel plugins: {self.kernel.plugins}")

        except Exception as e:
            logger.error("Failed to initialize plugins", exc_info=e)
            raise self._create_agent_error(
                message="Failed to initialize plugins",
                context=context,
                cause=e,
                recovery_hint="Check plugin configuration",
            ) from e

    async def _build_prompt_context(self, message: Message) -> str:
        """Build the prompt context including plugin instructions.

        Args:
            message: The current message being processed

        Returns:
            The complete prompt context
        """
        # Start with system prompt
        context = self.config.system_prompt
        logger.debug("Building prompt context starting with system prompt")

        # Add plugin instructions if we have plugins
        if self.plugin_manager and self.plugin_manager.plugins:
            plugin_instructions = []
            for plugin_class, plugin_instance in self.plugin_manager.plugins.values():
                if plugin_instance.plugin_instructions:
                    plugin_instructions.append(
                        f"{plugin_instance.name}: {plugin_instance.plugin_instructions}"
                    )

            if plugin_instructions:
                context += "\n\nAvailable plugins:\n" + "\n".join(plugin_instructions)
                logger.debug(
                    f"Added plugin instructions to context: {plugin_instructions}"
                )

        return context

    async def process_message(
        self, message: Message, context: ConversationContext
    ) -> AsyncGenerator[str, None]:
        """Process a message and generate responses"""
        # Initialize operation_context to None before the try block
        operation_context = None

        try:
            # Create operation context with the correct context.id
            operation_context = await self._handle_agent_operation(
                "process_message", message_type=message.role, context_id=context.id
            )
            logger.debug("Processing message with context: %s", operation_context)

            if not self.provider:
                raise RuntimeError("Agent not initialized")

            # Add message to context
            await context.add_message(message)
            logger.debug("Added message to context")

            # Build prompt context with plugins
            prompt_context = await self._build_prompt_context(message)
            logger.debug(f"Built prompt context: {prompt_context[:100]}...")

            # Get chat history from context
            history = context.get_history()
            logger.debug(f"Chat history has {len(history.messages)} messages")

            # Add system prompt if not already present
            if not any(msg.role == "system" for msg in history.messages):
                history.add_system_message(prompt_context)
                logger.debug("Added system prompt to history")

            async def _process():
                try:
                    # Create settings for function calling
                    from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.open_ai_prompt_execution_settings import (
                        OpenAIChatPromptExecutionSettings,
                    )
                    from semantic_kernel.connectors.ai.function_choice_behavior import (
                        FunctionChoiceBehavior,
                    )

                    logger.debug("Creating OpenAI chat settings")
                    settings = OpenAIChatPromptExecutionSettings(
                        temperature=self.config.model.temperature,
                        max_tokens=self.config.model.max_tokens,
                        top_p=self.config.model.top_p,
                        frequency_penalty=self.config.model.frequency_penalty,
                        presence_penalty=self.config.model.presence_penalty,
                        function_choice_behavior=FunctionChoiceBehavior.Auto(),
                    )
                    logger.debug(f"Created settings: {settings}")

                    # Create arguments for the chat function
                    from semantic_kernel.functions import KernelArguments

                    arguments = KernelArguments(
                        chat_history=history,
                        user_input=message.content,
                        settings=settings,
                    )
                    logger.debug(
                        f"Created kernel arguments with user input: {message.content[:50]}..."
                    )

                    # Stream the response
                    streamed_assistant_chunks = []
                    streamed_tool_chunks = []
                    complete_assistant_response = ""

                    logger.info("Invoking kernel with ChatBot.Chat function")
                    try:
                        async for result in self.kernel.invoke_stream(
                            plugin_name="ChatBot",
                            function_name="Chat",
                            arguments=arguments,
                            return_function_results=True,
                        ):
                            logger.debug(f"Received result type: {type(result)}")
                            if isinstance(result, list) and len(result) > 0:
                                msg = result[0]
                                logger.debug(
                                    f"Result item type: {type(msg)}, role: {getattr(msg, 'role', 'unknown')}"
                                )

                                if isinstance(msg, StreamingChatMessageContent):
                                    if msg.role == AuthorRole.ASSISTANT:
                                        # This is a standard assistant message - collect and yield it
                                        streamed_assistant_chunks.append(msg)
                                        chunk_text = str(msg)
                                        complete_assistant_response += chunk_text
                                        logger.debug(f"Assistant chunk: {chunk_text}")
                                        yield chunk_text
                                    elif msg.role == AuthorRole.TOOL:
                                        # This is a tool/function message - collect but don't yield
                                        logger.debug(f"Tool message received: {msg}")
                                        # Log extra details about the tool message
                                        if hasattr(msg, "function_invoke_attempt"):
                                            logger.debug(
                                                f"Tool message has function_invoke_attempt: {getattr(msg, 'function_invoke_attempt')}"
                                            )
                                        if hasattr(msg, "items"):
                                            logger.debug(
                                                f"Tool message items: {getattr(msg, 'items')}"
                                            )
                                        streamed_tool_chunks.append(msg)
                                        # Don't yield tool messages to avoid mixing message types
                                    else:
                                        logger.debug(
                                            f"Other message type with role {msg.role}: {msg}"
                                        )
                    except ContentAdditionException as e:
                        # Handle the ContentAdditionException gracefully
                        logger.warning(
                            f"ContentAdditionException occurred: {e}. This is expected when mixing message roles."
                        )
                        # Log more details about the exception
                        logger.warning(f"Exception details: {str(e)}")
                        logger.warning(f"Exception type: {type(e).__name__}")
                        # We've already yielded the text chunks, so we can continue
                    except Exception as e:
                        logger.error(f"Error during streaming: {e}", exc_info=e)
                        yield f"\n\nError during streaming: {str(e)}"

                    # Process tool messages if any
                    if streamed_tool_chunks:
                        logger.debug(
                            f"Processing {len(streamed_tool_chunks)} tool messages"
                        )
                        try:
                            # Group tool chunks by function_invoke_attempt if available
                            grouped_chunks = {}
                            for chunk in streamed_tool_chunks:
                                key = getattr(chunk, "function_invoke_attempt", 0)
                                if key not in grouped_chunks:
                                    grouped_chunks[key] = []
                                grouped_chunks[key].append(chunk)

                            # Log tool calls for debugging
                            for attempt, chunks in grouped_chunks.items():
                                logger.debug(
                                    f"Tool call attempt {attempt} with {len(chunks)} chunks"
                                )
                                # Log the content of the first chunk for diagnostics
                                if chunks:
                                    first_chunk = chunks[0]
                                    logger.debug(
                                        f"First chunk in attempt {attempt}: {first_chunk}"
                                    )
                                    if hasattr(first_chunk, "content"):
                                        logger.debug(f"Content: {first_chunk.content}")
                                    if hasattr(first_chunk, "items"):
                                        logger.debug(f"Items: {first_chunk.items}")
                                # We don't need to do anything with these right now
                                # In the future, we could process these tool calls
                        except Exception as e:
                            logger.error(
                                f"Error processing tool chunks: {e}", exc_info=e
                            )

                    # After streaming is complete, add the assistant's complete response to history
                    if streamed_assistant_chunks:
                        logger.debug(
                            f"Adding assistant response to history: {complete_assistant_response[:50]}..."
                        )
                        logger.debug(
                            f"Chat history before adding response has {len(history.messages)} messages"
                        )
                        await context.add_message(
                            Message(
                                content=complete_assistant_response, role="assistant"
                            )
                        )
                        logger.debug(
                            f"Chat history after adding response has {len(history.messages)} messages"
                        )
                except Exception as e:
                    logger.error("Error executing chat function", exc_info=e)
                    yield f"\n\nError executing chat function: {str(e)}"

            # Use the retry handler with the process function
            async for chunk in self.retry_handler.retry_generator(
                _process, operation_context
            ):
                yield chunk

        except Exception as e:
            # Ensure we have a default operation_context if we failed before creating one
            if operation_context is None:
                operation_context = ErrorContext(
                    component="agent",
                    operation="process_message",
                    details={
                        "agent_id": self.id,
                        "message_type": getattr(message, "role", "unknown"),
                        "error": str(e),
                    },
                )

            logger.error(
                "Error processing message", extra={"error": str(e)}, exc_info=e
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
