# agent_runtime/providers/openai.py
import logging
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
from agent_runtime.planners import PlannerType, get_planner

logger = logging.getLogger(__name__)


class OpenAIProvider(Provider):
    """OpenAI provider implementation with function-calling and stepwise planning support."""

    def __init__(self, config: ProviderConfig, base_dir: Optional[Path] = None):
        """Initialize OpenAI provider with optional base directory for plugins."""
        super().__init__(config)
        if not isinstance(self.settings, OpenAISettings):
            raise ValueError("Invalid settings type for OpenAI provider")

        self.model = config.model or "gpt-3.5-turbo"
        self.client = OpenAIChatCompletion(ai_model_id=self.model)
        self.service_id = "openai"  # Used for both chat and planning
        self.base_dir = base_dir

        # Initialize planner
        self.planner = get_planner(PlannerType.STEPWISE, logger=logger)

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

    async def plan_and_execute(
        self,
        goal: str,
        kernel: Optional[Kernel] = None,
    ) -> AsyncIterator[StreamingChatMessageContent]:
        """Execute tasks using the configured planner."""
        if not kernel:
            kernel = Kernel()

        # Configure settings for planning
        settings = OpenAIChatPromptExecutionSettings(
            temperature=self.settings.temperature,
            top_p=self.settings.top_p,
            max_tokens=self.settings.max_tokens,
            enable_function_calling=True,
        )

        try:
            # Use our planner to handle the request
            result = await self.planner.plan_and_execute(goal, kernel, settings)

            # Yield the result as a streaming message
            yield StreamingChatMessageContent(
                role="assistant", content=result, choice_index=0
            )
        except Exception as e:
            logger.error(f"Error in plan_and_execute: {str(e)}")
            yield StreamingChatMessageContent(
                role="assistant",
                content=f"Error during planning: {str(e)}",
                choice_index=0,
            )
