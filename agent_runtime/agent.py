"""Agent implementation for Agent Foundry with a lockfile-based plugin approach."""

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

from agent_runtime.plugins.manager import PluginConfig


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

        # Store config
        self.model_config = model_config
        self.plugins_dir = plugins_dir
        self.logger.debug("Agent '%s' initialized.", self.name)

    def _setup_chat_service(
        self, model_config: Dict[str, Any]
    ) -> Union[OpenAIChatCompletion, OllamaChatCompletion]:
        """Set up the chat completion service based on provider."""
        self.logger.debug("Setting up chat service with model config: %s", model_config)

        if isinstance(model_config, str):
            self.logger.error("Model config is a string: %s", model_config)
            raise ValueError("Model config is not resolved properly")

        provider = model_config.get("provider")
        model_name = model_config.get("name")

        if not provider or not model_name:
            self.logger.error("Model config missing required fields: %s", model_config)
            raise ValueError("Model config missing required fields: provider, name")

        if provider == "openai":
            self.logger.debug("Initializing OpenAI with model: %s", model_name)
            return OpenAIChatCompletion(ai_model_id=model_name)
        elif provider == "ollama":
            self.logger.debug("Initializing Ollama with model: %s", model_name)
            return OllamaChatCompletion(ai_model_id=model_name)
        else:
            raise ValueError(f"Unsupported model provider: {provider}")

    @classmethod
    def from_config(
        cls,
        config: Dict[str, Any],
        base_dir: Optional[Path] = None,
        lockfile_name: str = "plugins.lock.json",
        skip_init: bool = False,
    ) -> "Agent":
        """Create an agent from config.

        If skip_init=True, skip plugin installation checks.
        This relies on CLI commands (or other processes) having already run 'init' if needed.

        Args:
            config: The agent configuration dictionary
            base_dir: Optional base directory for resolving paths
            lockfile_name: Name of the lockfile (default: plugins.lock.json)
            skip_init: Whether to skip plugin installation checks

        Returns:
            The initialized Agent instance
        """
        logger = logging.getLogger("agent_runtime")
        logger.debug(
            "Creating agent from config at '%s'. skip_init=%s", base_dir, skip_init
        )
        logger.debug("Agent config: %s", config)

        kernel = Kernel()

        # Build plugin configs here just for clarity, but do not install
        # or load them automatically unless skip_init==False (which we
        # typically do in an 'init' workflow). The CLI is handling that logic.
        plugin_data = config.get("plugins", [])
        logger.debug("Plugin data: %s", plugin_data)

        configs = []
        for p in plugin_data:
            try:
                if isinstance(p, dict) and all(
                    k in p for k in ["type", "name", "source"]
                ):
                    c = PluginConfig(
                        plugin_type=p["type"],
                        name=p["name"],
                        source=p["source"],
                        version=p.get("version"),
                        variables=p.get("variables", {}),
                    )
                    configs.append(c)
                else:
                    logger.debug("Skipping unresolved plugin reference: %s", p)
            except (KeyError, ValueError) as ex:
                logger.error("Invalid plugin config: %s", ex)

        # Create the agent instance with the new kernel.
        # We assume plugins have been loaded externally if skip_init=True.
        logger.debug("Creating agent with model config: %s", config["model"])
        agent = cls(
            name=config["name"],
            description=config["description"],
            system_prompt=config["system_prompt"],
            model_config=config["model"],
            kernel=kernel,
            plugins_dir=base_dir,
        )
        return agent

    async def chat(self, message: str) -> AsyncIterator[StreamingChatMessageContent]:
        """Generate a chat response from the agent.

        Args:
            message: The user's input message

        Yields:
            Chat message content chunks as they are generated
        """
        self.logger.debug("Agent '%s' received message: %s", self.name, message)
        self.chat_history.add_user_message(message)

        # List plugin functions
        for pname, plugin in self.kernel.plugins.items():
            self.logger.debug(
                "Plugin '%s' functions: %s", pname, list(plugin.functions.keys())
            )

        # Attempt plugin function match
        for pname, plugin in self.kernel.plugins.items():
            for fname, func in plugin.functions.items():
                if message.lower().startswith(fname.lower()):
                    self.logger.debug("Matched plugin function '%s.%s'", pname, fname)
                    arg = message[len(fname) :].strip() or "World"

                    from semantic_kernel.functions import KernelArguments

                    args = KernelArguments()

                    if func.parameters:
                        param_name = func.parameters[0].name
                        args[param_name] = arg

                    try:
                        result = await func.invoke(kernel=self.kernel, arguments=args)
                        yield StreamingChatMessageContent(
                            role=AuthorRole.ASSISTANT,
                            content=str(result),
                            choice_index=0,
                        )
                        self.chat_history.add_assistant_message(str(result))
                        return
                    except Exception as e:
                        err_msg = f"Function '{fname}' failed: {e}"
                        self.logger.error(err_msg)
                        yield StreamingChatMessageContent(
                            role=AuthorRole.ASSISTANT, content=err_msg, choice_index=0
                        )
                        return

        # Fallback to chat model
        self.logger.debug("No function matched; using chat service for response.")
        settings = self.model_config.get("settings", {})
        exec_settings = PromptExecutionSettings(
            service_id=None,
            extension_data={},
            temperature=settings.get("temperature", 0.7),
            top_p=settings.get("top_p", 1.0),
            max_tokens=settings.get("max_tokens"),
        )

        last_chunk = None
        async for chunk in self.chat_service.get_streaming_chat_message_content(
            chat_history=self.chat_history,
            settings=exec_settings,
        ):
            if chunk:
                yield chunk
                last_chunk = chunk

        if last_chunk:
            self.chat_history.add_assistant_message(last_chunk.content)
