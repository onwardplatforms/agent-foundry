from abc import ABC, abstractmethod
from typing import Any, Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.open_ai_prompt_execution_settings import (
    OpenAIChatPromptExecutionSettings,
)


class BasePlanner(ABC):
    """Base class for all planners that handle task planning and execution."""

    def __init__(self, logger=None):
        self.logger = logger

    @abstractmethod
    async def plan_and_execute(
        self, goal: str, kernel: Kernel, settings: Optional[Any] = None
    ) -> str:
        """
        Plan and execute steps to achieve the given goal.

        Args:
            goal: The goal or task to accomplish
            kernel: Semantic Kernel instance with loaded plugins
            settings: Model-specific settings for execution

        Returns:
            The final result or response
        """
        pass
