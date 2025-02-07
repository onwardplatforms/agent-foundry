"""Web capability implementation using Semantic Kernel."""

from typing import Any, Dict, Optional

import aiohttp
from semantic_kernel import Kernel
from semantic_kernel.skill_definition import sk_function, sk_function_context_parameter

from agent_runtime.capabilities.base import BaseCapability


class WebCapability(BaseCapability):
    """Web capability for fetching web pages and performing HTTP requests."""

    def __init__(self) -> None:
        """Initialize the web capability."""
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def name(self) -> str:
        """Get the name of the capability."""
        return "web"

    @property
    def description(self) -> str:
        """Get the description of the capability."""
        return "Enables fetching web pages and making HTTP requests"

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Define the configuration schema for this capability."""
        return {}

    def get_prompt_description(self) -> str:
        """Get the description to be included in the agent's system prompt."""
        return (
            "The web plugin provides functions for fetching web pages and making HTTP requests.\n\n"
            "Function: fetch_page(url: str)\n"
            "Description: Fetches the content of a web page at the given URL\n"
            "Parameters:\n"
            "- url: The URL of the web page to fetch\n\n"
            "Example usage:\n"
            '- fetch_page("https://example.com")\n'
        )

    async def initialize(
        self, config: Dict[str, Any], kernel: Optional[Kernel] = None
    ) -> None:
        """Initialize the web capability.

        Args:
            config: Configuration dictionary with capability settings
            kernel: Optional kernel instance for registering plugins

        Raises:
            ValueError: If kernel is not provided
        """
        if not kernel:
            raise ValueError("Kernel is required for Web capability")

        # Create HTTP session
        self._session = aiohttp.ClientSession()

        # Register the plugin functions with the kernel
        kernel.import_skill(self, skill_name="web")

    async def cleanup(self) -> None:
        """Clean up resources used by the capability."""
        if self._session:
            await self._session.close()
            self._session = None

    @sk_function(
        description="Fetches the content of a web page",
        name="fetch_page",
    )
    @sk_function_context_parameter(
        name="url",
        description="The URL of the web page to fetch",
    )
    async def fetch_page(self, url: str) -> str:
        """Fetch the content of a web page.

        Args:
            url: The URL of the web page to fetch

        Returns:
            The content of the web page as text

        Raises:
            ValueError: If the session is not initialized
            aiohttp.ClientError: If the request fails
        """
        if not self._session:
            raise ValueError("HTTP session not initialized")

        async with self._session.get(url) as response:
            response.raise_for_status()
            return await response.text()
