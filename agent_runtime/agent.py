# agent_runtime/agent.py
"""Agent implementation for Agent Foundry with a lockfile-based plugin approach."""

import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

from semantic_kernel import Kernel
from semantic_kernel.contents import ChatHistory, StreamingChatMessageContent

from agent_runtime.plugins.manager import PluginManager

logger = logging.getLogger(__name__)


class Agent:
    """Agent class for interacting with AI models."""

    def __init__(
        self,
        name: str,
        description: str,
        system_prompt: str,
        provider,  # Polymorphic provider (OpenAIProvider, OllamaProvider, etc.)
        base_dir: Optional[Path] = None,
        skip_init: bool = False,
    ):
        """Initialize the agent."""
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.provider = provider
        self.base_dir = base_dir
        self.kernel: Optional[Kernel] = None
        self.history = ChatHistory()
        self.history.add_system_message(system_prompt)

        # If skip_init=False and we have a base directory, load plugins
        if not skip_init and base_dir:
            self._init_plugins()

    def _init_plugins(self) -> None:
        """Initialize plugins for the agent and fetch their instructions."""
        if not self.base_dir:
            return

        self.kernel = Kernel()
        pm = PluginManager(self.base_dir, self.kernel)
        pm.load_all_plugins()

        # Fetch instructions from each plugin and incorporate them
        plugin_instructions = []
        for plugin in self.kernel.plugins.values():
            try:
                # Try to get instructions using the get_instructions function
                if hasattr(plugin, "get_instructions"):
                    instructions = plugin.get_instructions()
                    if instructions:
                        plugin_instructions.append(
                            f"\nInstructions for {plugin.name} plugin:\n{instructions}"
                        )
            except Exception as e:
                logger.warning(
                    f"Failed to get instructions from plugin {plugin.name}: {e}"
                )

        # Append plugin instructions to system prompt if any were found
        if plugin_instructions:
            combined_instructions = "\n".join(plugin_instructions)
            self.system_prompt = f"{self.system_prompt}\n\nPlugin-specific Instructions:{combined_instructions}"
            # Update the chat history with new system prompt
            self.history = ChatHistory()
            self.history.add_system_message(self.system_prompt)
            logger.debug("Added plugin instructions to system prompt")

    def start_new_session(self) -> None:
        """Start a new chat session with a fresh history while preserving plugin instructions."""
        self.history = ChatHistory()
        self.history.add_system_message(
            self.system_prompt
        )  # system_prompt already includes plugin instructions
        logger.debug("Started new chat session for agent '%s'", self.name)
        logger.debug("System prompt: %s", self.system_prompt)

    def _log_chat_history(self, prefix: str = "") -> None:
        """Log the current state of the chat history (for debugging)."""
        logger.debug("%sChat history:", prefix)
        for i, msg in enumerate(self.history.messages):
            logger.debug("%s  [%d] %s: %s", prefix, i, msg.role, msg.content)

    async def _execute_function(self, function_call: Dict[str, Any]) -> str:
        """Execute a function call and return the result."""
        if not self.kernel:
            return "Error: No kernel available for function execution"

        try:
            # Example function_call dict:
            # {"name": "pluginName_functionName", "arguments": "{\"argKey\":\"argValue\"}"}
            func_name = function_call["name"]
            arguments_json = function_call.get("arguments", "{}")
            arguments = json.loads(arguments_json)

            # The function name is "pluginName_functionName"
            plugin_name, func_name = func_name.split("_", 1)

            plugin = self.kernel.plugins.get(plugin_name)
            if not plugin:
                return f"Error: Plugin '{plugin_name}' not found"

            func = plugin.functions.get(func_name)
            if not func:
                return (
                    f"Error: Function '{func_name}' not found in plugin '{plugin_name}'"
                )

            # Build KernelArguments
            from semantic_kernel.functions import KernelArguments

            kernel_args = KernelArguments()
            for k, v in arguments.items():
                kernel_args[k] = v

            # Execute the function
            result = await func.invoke(kernel=self.kernel, arguments=kernel_args)
            return str(result)

        except Exception as e:
            logger.exception("Error executing function")
            return f"Error executing function: {str(e)}"

    async def chat(self, message: str) -> AsyncIterator[StreamingChatMessageContent]:
        """
        Process a chat message by passing the conversation history to the provider.
        If the provider yields a chunk with a function call, run _execute_function,
        then continue the conversation with the function's result.
        """
        # Add the user's message to the history
        self.history.add_user_message(message)

        # 1. Ask our provider to produce a streaming response (chunks).
        async for chunk in self.provider.chat(self.history, kernel=self.kernel):
            if chunk is None:
                continue

            # 2. If we detect a function call from the provider:
            if hasattr(chunk, "function_call") and chunk.function_call:
                # Execute the function
                result = await self._execute_function(chunk.function_call)

                # Add function call and result to our conversation
                self.history.add_assistant_message(
                    content="", function_call=chunk.function_call
                )
                self.history.add_function_message(
                    name=chunk.function_call["name"], content=result
                )

                # 3. Continue the conversation with the function result appended
                async for response_chunk in self.provider.chat(
                    self.history, kernel=self.kernel
                ):
                    yield response_chunk

            else:
                # Normal text chunk
                yield chunk

        # 4. Once complete, if the last chunk had text, add it to history
        if chunk and hasattr(chunk, "content") and chunk.content:
            self.history.add_assistant_message(chunk.content)
            self._log_chat_history("After model response: ")

    @classmethod
    def from_config(
        cls,
        config: Dict[str, Any],
        base_dir: Optional[Path] = None,
        skip_init: bool = False,
    ) -> "Agent":
        """
        Create an agent from a config dictionary.

        Expects a structure like:
        {
            "name": "AgentName",
            "description": "...",
            "system_prompt": "...",
            "model": {
                "provider": "openai" or "ollama",
                "name": "gpt-3.5-turbo" or "llama2",
                "settings": [ ... ]  # optional
            }
        }
        """
        from agent_runtime.providers.base import ProviderConfig, ProviderType

        # Extract model info
        model_config = config.get("model", {})
        if isinstance(model_config, dict):
            provider_type = model_config.get("provider", "openai")
            model_name = model_config.get("name", "gpt-3.5-turbo")
            # "settings" might be a list of dicts; take the first if present
            model_settings = (model_config.get("settings", [{}]) or [{}])[0]
        else:
            provider_type = "openai"
            model_name = "gpt-3.5-turbo"
            model_settings = {}

        # Build provider config
        provider_config = ProviderConfig(
            name=ProviderType(provider_type),
            model=model_name,
            settings=model_settings,
            agent_id=config.get("name"),
        )

        # Instantiate the correct provider
        if provider_type == "ollama":
            from agent_runtime.providers.ollama import OllamaProvider

            provider = OllamaProvider(provider_config)
        else:
            from agent_runtime.providers.openai import OpenAIProvider

            # IMPORTANT: Pass base_dir, so the provider can use it for PluginManager
            provider = OpenAIProvider(provider_config, base_dir=base_dir)

        return cls(
            name=config["name"],
            description=config.get("description", ""),
            system_prompt=config["system_prompt"],
            provider=provider,
            base_dir=base_dir,
            skip_init=skip_init,
        )
