import traceback
from typing import Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.open_ai_prompt_execution_settings import (
    OpenAIChatPromptExecutionSettings,
)
from semantic_kernel.contents.chat_history import ChatHistory

from .base import BasePlanner


class StepwisePlanner(BasePlanner):
    """Implements stepwise planning using OpenAI's function calling capabilities."""

    async def _add_chat_history_to_goal(self, goal: str, kernel: Kernel) -> str:
        # Get chat history from kernel plugins
        history = None
        for plugin in kernel.plugins:
            if isinstance(plugin, ChatHistory):
                history = plugin
                break

        if history and history.messages:
            context = "\nPrevious conversation:\n"
            for msg in history.messages:
                context += f"{msg.role}: {msg.content}\n"
            return goal + context
        return goal

    async def plan_and_execute(
        self,
        goal: str,
        kernel: Kernel,
        settings: Optional[OpenAIChatPromptExecutionSettings] = None,
    ) -> str:
        try:
            # Add chat history context to goal if available
            goal_with_context = await self._add_chat_history_to_goal(goal, kernel)

            if not settings:
                settings = OpenAIChatPromptExecutionSettings()

            # Load function definitions for planner if enabled
            if settings.enable_function_calling:
                functions = await kernel.plugins.get_openai_functions()
                self.logger.debug(f"Loaded {len(functions)} functions for planner")
                settings.functions = functions

            self.logger.debug("Creating plan...")
            result = await kernel.invoke_prompt(goal_with_context, settings=settings)

            # Extract final answer from result
            if hasattr(result, "final_answer"):
                return result.final_answer
            return str(result)

        except Exception as e:
            self.logger.error(f"Error during planning:\n{traceback.format_exc()}")
            raise ValueError(f"Error in stepwise planning: {str(e)}")
