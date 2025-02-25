"""Example hello world plugin demonstrating the plugin system."""

from typing import Optional
from semantic_kernel.functions import kernel_function

from agent_runtime_v2.plugins.base import Plugin, PluginVariable


class HelloPlugin(Plugin):
    """A simple hello world plugin for testing the agent system."""

    name = "hello"
    description = "A simple plugin that says hello"
    plugin_instructions = """
    Use this plugin when you need to:
    - Greet someone with a simple hello message
    - Greet the world if no specific person is mentioned
    """

    # Define a default_name variable that can be configured
    default_name = PluginVariable(
        type=str,
        description="The default name to use when no name is provided",
        default="World",
    )

    @kernel_function(description="Say hello to someone or the world")
    def greet(self, name: Optional[str] = None) -> str:
        """Greet someone by name, or say Hello to the default name if no name is provided.

        Args:
            name: The name of the person to greet (optional)

        Returns:
            A simple greeting
        """
        if name:
            return f"Hello, {name}!"
        else:
            return f"Hello, {self.default_name}!"
