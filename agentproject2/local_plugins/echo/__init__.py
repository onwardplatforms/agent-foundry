"""Local test plugin package."""

from semantic_kernel.functions import kernel_function


class TestPlugin:
    """A test plugin with some basic functions."""

    @classmethod
    def get_plugin_info(cls):
        """Get plugin information."""
        return {
            "name": "test_plugin",
            "description": "A test plugin with basic text manipulation functions",
        }

    @kernel_function(description="Greet someone by name", name="greet")
    def greet(self, name: str) -> str:
        """Greet someone by name.

        Args:
            name: The name of the person to greet

        Returns:
            A greeting message
        """
        return f"Hello, {name}! Nice to meet you! (from local plugin)"

    @kernel_function(description="Echo back the input", name="echo")
    def echo(self, input: str) -> str:
        """Echo back the input.

        Args:
            input: The text to echo

        Returns:
            The same text that was input
        """
        return f"{input} (from local plugin)"

    @kernel_function(
        description="Sign a message with the configured signature", name="sign"
    )
    def sign(self, message: str, signature: str = "Anonymous") -> str:
        """Sign a message with a signature.

        Args:
            message: The message to sign
            signature: The signature to use (defaults to Anonymous)

        Returns:
            The signed message
        """
        return f"{message}\n\n(from local plugin)\n\nBest regards,\n{signature}"
