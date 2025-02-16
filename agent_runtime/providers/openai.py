# agent_runtime/providers/openai.py
from pathlib import Path
from typing import AsyncIterator, Optional, Dict, Any

from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.open_ai_prompt_execution_settings import (
    OpenAIChatPromptExecutionSettings,
)
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel.contents import ChatHistory, StreamingChatMessageContent
from semantic_kernel.kernel import Kernel

from agent_runtime.providers.base import OpenAISettings, Provider, ProviderConfig
from agent_runtime.plugins.manager import PluginManager


class OpenAIProvider(Provider):
    """OpenAI provider implementation with function-calling support."""

    def __init__(self, config: ProviderConfig, base_dir: Optional[Path] = None):
        """
        Store the base_dir so we can load plugin-based function definitions from
        the same folder the Agent is using.
        """
        super().__init__(config)
        if not isinstance(self.settings, OpenAISettings):
            raise ValueError("Invalid settings type for OpenAI provider")

        self.model = config.model or "gpt-3.5-turbo"
        self.client = OpenAIChatCompletion(ai_model_id=self.model)

        # For loading plugins (function definitions), we need the same base_dir as the agent
        self.base_dir = base_dir

    async def chat(
        self,
        history: ChatHistory,
        kernel: Optional[Kernel] = None,
        functions: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[StreamingChatMessageContent]:
        """
        Stream a chat response from OpenAI.
        If function definitions are available, attach them to the settings.
        """

        # If no kernel is given, create a new one.
        if not kernel:
            kernel = Kernel()

        # Build the prompt execution settings for OpenAI
        settings = OpenAIChatPromptExecutionSettings(
            temperature=self.settings.temperature,
            top_p=self.settings.top_p,
            max_tokens=self.settings.max_tokens,
            function_choice_behavior=FunctionChoiceBehavior.Auto(),
        )

        # If we have a valid base_dir and a kernel with plugins,
        # load the OpenAI function definitions from our plugin manager.
        if self.base_dir and hasattr(kernel, "plugins"):
            pm = PluginManager(self.base_dir, kernel)
            openai_funcs = pm.get_openai_functions()
            if openai_funcs:
                # 'functions' is a list of JSON schema definitions for each function
                settings.tools = openai_funcs.get("functions", [])
                # 'function_call' can be "auto" or "none" or a specific function name
                settings.tool_choice = openai_funcs.get("function_call", "auto")

        # Now request a streaming response from the OpenAI model
        async for chunk in self.client.get_streaming_chat_message_content(
            chat_history=history,
            settings=settings,
            kernel=kernel,
        ):
            # If the chunk includes a function call, yield that chunk with chunk.function_call
            if hasattr(chunk, "function_call") and chunk.function_call:
                yield chunk
            else:
                # Normal text chunk
                yield chunk
