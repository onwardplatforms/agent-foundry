"""Base capability interface for Agent Foundry."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from semantic_kernel import Kernel


class BaseCapability(ABC):
    """Base class for all capabilities."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the name of the capability."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Get the description of the capability."""
        pass

    @abstractmethod
    def get_prompt_description(self) -> str:
        """Get the description to be included in the agent's system prompt."""
        pass

    @abstractmethod
    async def initialize(
        self, config: Optional[Dict[str, Any]] = None, kernel: Optional[Kernel] = None
    ) -> None:
        """Initialize the capability with configuration.

        Args:
            config: Optional configuration dictionary
            kernel: Optional kernel instance for registering plugins
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up resources used by the capability."""
        pass
