"""Google search capability implementation."""

from typing import Any, Dict, Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.search_engine import GoogleConnector
from semantic_kernel.core_plugins import WebSearchEnginePlugin

from agent_foundry.capabilities.base import BaseCapability
from agent_foundry.env import get_env_var


class GoogleSearchCapability(BaseCapability):
    """Google search capability using Custom Search API."""

    def __init__(self) -> None:
        """Initialize the Google search capability."""
        self._plugin: Optional[WebSearchEnginePlugin] = None

    @property
    def name(self) -> str:
        """Get the name of the capability."""
        return "GoogleSearch"

    @property
    def description(self) -> str:
        """Get the description of the capability."""
        return "Enables web search using Google Custom Search API"

    def get_prompt_description(self) -> str:
        """Get the description to be included in the agent's system prompt."""
        return (
            "The GoogleSearch plugin provides real-time web search functionality.\n\n"
            "Function: search(query: str, num_results: int = 1, offset: int = 0)\n"
            "Description: Searches the web using Google Custom Search and returns "
            "results\n"
            "Parameters:\n"
            "- query: The search query string\n"
            "- num_results: Number of results to return (default: 1)\n"
            "- offset: Number of results to skip (default: 0)\n\n"
            "Example usage:\n"
            '- search("current weather in Dallas, TX")\n'
            '- search("latest news about OpenAI", num_results=5)\n'
            '- search("population of Tokyo 2024", num_results=3, offset=2)\n\n'
            "The function returns snippets from relevant web pages, "
            "including titles and descriptions."
        )

    async def initialize(
        self, config: Optional[Dict[str, Any]] = None, kernel: Optional[Kernel] = None
    ) -> None:
        """Initialize the Google search capability.

        Args:
            config: Optional configuration dictionary
            kernel: Optional kernel instance for registering plugins

        Raises:
            ValueError: If kernel is not provided or credentials are missing
        """
        if not kernel:
            raise ValueError("Kernel is required for Google Search capability")

        # Get credentials from environment
        api_key = get_env_var("GOOGLE_API_KEY", None)
        search_engine_id = get_env_var("GOOGLE_SEARCH_ENGINE_ID", None)

        if not api_key or not search_engine_id:
            raise ValueError(
                "Google Search API credentials not found. "
                "Please set GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID "
                "environment variables."
            )

        # Create Google connector
        connector = GoogleConnector(
            api_key=api_key,
            search_engine_id=search_engine_id,
        )

        # Create and register the plugin
        self._plugin = WebSearchEnginePlugin(connector)
        kernel.add_plugin(self._plugin, plugin_name="WebSearch")

    async def cleanup(self) -> None:
        """Clean up resources used by the capability."""
        self._plugin = None
