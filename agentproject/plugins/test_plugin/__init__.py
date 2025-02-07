"""Test plugin package."""

from semantic_kernel.functions import kernel_function


class TestPlugin:
    """A test plugin with some basic functions."""

    @kernel_function(description="Greet someone by name", name="greet")
    def greet(self, name: str) -> str:
        """Greet someone by name.

        Args:
            name: The name of the person to greet

        Returns:
            A greeting message
        """
        return f"Hello, {name}! Nice to meet you!"

    @kernel_function(description="Echo back the input", name="echo")
    def echo(self, input: str) -> str:
        """Echo back the input.

        Args:
            input: The text to echo

        Returns:
            The same text that was input
        """
        return input
