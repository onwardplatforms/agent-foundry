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
    - Greet generically using the configured default_name when no specific person is mentioned
    - For generic greetings with no target name, use the greet function without arguments to use the default_name
    """

    # Define a default_name variable that can be configured
    default_name = PluginVariable(
        type=str,
        description="The default name to use when no name is provided",
        default="World",
    )

    @kernel_function(
        description="Greet someone by name, or use the configured default_name if no name is provided"
    )
    def greet(self, name: Optional[str] = None) -> str:
        """Generate a friendly greeting message.

        When no specific name is provided, this will use the configured default_name value.
        For generic greetings, call this with no arguments to use the default_name.

        Args:
            name: The name of the person to greet (optional, uses default_name if not provided)

        Returns:
            A personalized greeting message
        """
        if name:
            return f"Hello, {name}!"
        else:
            return f"Hello, {self.default_name}!"
