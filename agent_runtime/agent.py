"""Agent implementation for Agent Foundry."""

import logging
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional, Union

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.ollama import OllamaChatCompletion
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.connectors.ai.prompt_execution_settings import (
    PromptExecutionSettings,
)
from semantic_kernel.contents import (
    AuthorRole,
    ChatHistory,
    StreamingChatMessageContent,
)

from agent_runtime.plugins.manager import PluginConfig, PluginManager


class Agent:
    """Agent class for interacting with AI models."""

    def __init__(
        self,
        name: str,
        description: str,
        system_prompt: str,
        model_config: Dict[str, Any],
        plugins_dir: Optional[Path] = None,
    ):
        """Initialize the agent.

        Args:
            name: Agent name
            description: Agent description
            system_prompt: System prompt for the agent
            model_config: Model configuration dictionary
            plugins_dir: Optional directory containing plugins
        """
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.logger = logging.getLogger("agent_runtime")

        # Initialize chat history
        self.chat_history = ChatHistory()
        self.chat_history.add_system_message(system_prompt)

        # Initialize kernel and chat completion service based on provider
        self.kernel = Kernel()
        self.chat_service = self._setup_chat_service(model_config)
        self.kernel.add_service(self.chat_service)

        # Store config for settings
        self.model_config = model_config
        self.plugins_dir = plugins_dir

    def _setup_chat_service(
        self, model_config: Dict[str, Any]
    ) -> Union[OpenAIChatCompletion, OllamaChatCompletion]:
        """Set up the chat completion service based on provider config.

        Args:
            model_config: Model configuration dictionary

        Returns:
            Configured chat completion service

        Raises:
            ValueError: If provider is not supported
        """
        provider = model_config["provider"]
        model_name = model_config["name"]
        settings = model_config.get("settings", {})

        if provider == "openai":
            self.logger.debug("Initializing OpenAI service with model: %s", model_name)
            return OpenAIChatCompletion(
                ai_model_id=model_name,
                temperature=settings.get("temperature", 0.7),
                max_tokens=settings.get("max_tokens"),
            )
        elif provider == "ollama":
            self.logger.debug("Initializing Ollama service with model: %s", model_name)
            return OllamaChatCompletion(ai_model_id=model_name)
        else:
            raise ValueError(f"Unsupported model provider: {provider}")

    @classmethod
    def from_config(cls, config: Dict[str, Any], base_dir: Path) -> "Agent":
        """Create an agent from a configuration dictionary.

        Args:
            config: Agent configuration dictionary
            base_dir: Base directory for resolving plugin paths

        Returns:
            Configured agent instance
        """
        # Create agent with basic config
        agent = cls(
            name=config["name"],
            description=config["description"],
            system_prompt=config["system_prompt"],
            model_config=config["model"],
            plugins_dir=base_dir / ".plugins",
        )

        # Set up plugins if any are configured
        if config.get("plugins"):
            plugin_manager = PluginManager(agent.kernel, base_dir)
            plugin_configs = [
                PluginConfig(
                    name=p["name"],
                    source=p["source"],
                    version=p.get("version"),
                    variables=p.get("variables"),
                )
                for p in config["plugins"]
            ]
            plugin_manager.install_and_load_plugins(plugin_configs, base_dir=base_dir)

        return agent

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

        # Debug: Log available plugins and functions
        self.logger.debug("Available plugins: %s", self.kernel.plugins)
        for plugin_name, plugin in self.kernel.plugins.items():
            self.logger.debug("Plugin %s functions: %s", plugin_name, plugin.functions)

        # Try to find a plugin function that matches the message
        # For example, if message starts with "greet", use the greet function
        for plugin_name, plugin in self.kernel.plugins.items():
            for func_name, func in plugin.functions.items():
                self.logger.debug("Checking function: %s", func_name)
                if message.lower().startswith(func_name.lower()):
                    self.logger.debug("Found matching function: %s", func_name)
                    # Extract the argument from the message
                    arg = message[len(func_name) :].strip()
                    if not arg:
                        arg = "World"  # Default argument

                    self.logger.debug("Function argument: %s", arg)

                    # Create arguments for the function
                    from semantic_kernel.functions import KernelArguments

                    # Get the parameter name from the function's first parameter
                    param_name = func.parameters[0].name
                    arguments = KernelArguments(**{param_name: arg})

                    try:
                        # Call the function
                        result = await func.invoke(
                            kernel=self.kernel, arguments=arguments
                        )

                        # Create a response chunk
                        yield StreamingChatMessageContent(
                            role=AuthorRole.ASSISTANT,
                            content=str(result),
                            choice_index=0,
                        )

                        # Add assistant's response to history
                        self.chat_history.add_assistant_message(str(result))
                        return
                    except Exception as e:
                        error_msg = f"Function failed. Error: {str(e)}"
                        self.logger.error(error_msg)
                        yield StreamingChatMessageContent(
                            role=AuthorRole.ASSISTANT, content=error_msg, choice_index=0
                        )
                        return

        # If no plugin function matches, use the chat service
        # Convert model settings to prompt execution settings
        settings = self.model_config.get("settings", {})
        execution_settings = PromptExecutionSettings(
            service_id=None,
            extension_data={},
            temperature=settings.get("temperature", 0.7),
            top_p=settings.get("top_p", 1.0),
            max_tokens=settings.get("max_tokens"),
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
