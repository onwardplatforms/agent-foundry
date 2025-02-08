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
        kernel: Optional[Kernel] = None,
        plugins_dir: Optional[Path] = None,
    ):
        """Initialize the agent.

        Args:
            name: Agent name
            description: Agent description
            system_prompt: System prompt for the agent
            model_config: Model configuration dictionary
            kernel: Optional pre-configured kernel with plugins
            plugins_dir: Optional directory containing plugins
        """
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.logger = logging.getLogger("agent_runtime")

        # Initialize chat history
        self.chat_history = ChatHistory()
        self.chat_history.add_system_message(system_prompt)

        # Initialize or use provided kernel
        self.kernel = kernel or Kernel()
        self.chat_service = self._setup_chat_service(model_config)
        self.kernel.add_service(self.chat_service)

        # Store config for settings
        self.model_config = model_config
        self.plugins_dir = plugins_dir

        self.logger.info("Agent '%s' initialized.", self.name)

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

        if provider == "openai":
            self.logger.debug("Initializing OpenAI service with model: %s", model_name)
            return OpenAIChatCompletion(ai_model_id=model_name)
        elif provider == "ollama":
            self.logger.debug("Initializing Ollama service with model: %s", model_name)
            return OllamaChatCompletion(ai_model_id=model_name)
        else:
            raise ValueError(f"Unsupported model provider: {provider}")

    @classmethod
    def from_config(
        cls, config: Dict[str, Any], base_dir: Optional[Path] = None
    ) -> "Agent":
        """Create an agent from a configuration dictionary.

        Args:
            config: Configuration dictionary
            base_dir: Optional base directory for resolving relative paths

        Returns:
            The created agent instance
        """
        logger = logging.getLogger("agent_runtime")
        logger.debug("Creating agent from config with base_dir=%s", base_dir)

        # Initialize a fresh kernel
        kernel = Kernel()
        plugin_manager = PluginManager(kernel, base_dir or Path.cwd())

        # Extract plugin configs from the agent config JSON
        plugin_data = config.get("plugins", [])
        logger.debug("Found %d plugin definitions in agent config.", len(plugin_data))

        plugin_configs = []
        for p in plugin_data:
            try:
                pc = PluginConfig(
                    source=p["source"],
                    version=p.get("version"),
                    branch=p.get("branch"),
                    variables=p.get("variables", {}),
                )
                plugin_configs.append(pc)
            except (KeyError, ValueError) as ex:
                logger.error("Invalid plugin configuration: %s", ex)
                continue

        # Install and load all plugins
        plugin_manager.install_and_load_plugins(plugin_configs, base_dir=base_dir)

        # Create agent instance with the configured kernel
        agent = cls(
            name=config["name"],
            description=config["description"],
            system_prompt=config["system_prompt"],
            model_config=config["model"],
            kernel=kernel,
            plugins_dir=base_dir,
        )
        logger.info("Agent '%s' created from config successfully.", agent.name)
        return agent

    async def chat(self, message: str) -> AsyncIterator[StreamingChatMessageContent]:
        """Process a chat message and return the response as a streaming generator.

        Args:
            message: User message

        Returns:
            Async generator of response chunks
        """
        self.logger.debug("Received user message: %s", message)
        self.chat_history.add_user_message(message)

        # Debug: Log available plugins and functions
        self.logger.debug(
            "Agent '%s' has %d plugins loaded.", self.name, len(self.kernel.plugins)
        )
        for plugin_name, plugin in self.kernel.plugins.items():
            self.logger.debug(
                "Plugin [%s] has functions: %s",
                plugin_name,
                list(plugin.functions.keys()),
            )

        # Attempt function matching based on message prefix
        for plugin_name, plugin in self.kernel.plugins.items():
            for func_name, func in plugin.functions.items():
                if message.lower().startswith(func_name.lower()):
                    self.logger.debug(
                        "Message matched plugin function '%s.%s'",
                        plugin_name,
                        func_name,
                    )

                    # Extract argument from the tail of the message
                    arg = message[len(func_name) :].strip()
                    if not arg:
                        arg = "World"  # Default argument for demonstration
                        self.logger.debug("No argument found; using default: '%s'", arg)

                    from semantic_kernel.functions import KernelArguments

                    try:
                        param_name = func.parameters[0].name
                    except IndexError:
                        self.logger.warning(
                            "Function '%s' expects no parameters, skipping argument assignment.",
                            func_name,
                        )
                        param_name = None

                    arguments = KernelArguments()
                    if param_name:
                        arguments[str(param_name)] = arg

                    try:
                        result = await func.invoke(
                            kernel=self.kernel, arguments=arguments
                        )
                        self.logger.debug(
                            "Function '%s.%s' returned: %s",
                            plugin_name,
                            func_name,
                            result,
                        )

                        # Yield streaming chunk
                        yield StreamingChatMessageContent(
                            role=AuthorRole.ASSISTANT,
                            content=str(result),
                            choice_index=0,
                        )
                        self.chat_history.add_assistant_message(str(result))
                        return
                    except Exception as e:
                        error_msg = (
                            f"Plugin function '{func_name}' failed. Error: {str(e)}"
                        )
                        self.logger.error(error_msg)
                        yield StreamingChatMessageContent(
                            role=AuthorRole.ASSISTANT, content=error_msg, choice_index=0
                        )
                        return

        # If no plugin function matches, fallback to the chat model
        self.logger.debug("No function matched, using chat service for agent response.")
        settings = self.model_config.get("settings", {})
        execution_settings = PromptExecutionSettings(
            service_id=None,
            extension_data={},
            temperature=settings.get("temperature", 0.7),
            top_p=settings.get("top_p", 1.0),
            max_tokens=settings.get("max_tokens"),
        )

        chunk = None
        async for chunk in self.chat_service.get_streaming_chat_message_content(
            chat_history=self.chat_history,
            settings=execution_settings,
        ):
            if chunk:
                yield chunk

        if chunk:
            self.chat_history.add_assistant_message(chunk.content)
