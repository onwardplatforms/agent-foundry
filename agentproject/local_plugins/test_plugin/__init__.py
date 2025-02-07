"""Local test plugin package."""

import os
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
    def sign(self, message: str) -> str:
        """Sign a message with the configured signature.

        Args:
            message: The message to sign

        Returns:
            The signed message
        """
        signature = os.getenv("AGENT_VAR_SIGNATURE", "Anonymous")
        return f"{message}\n\nBest regards,\n{signature}"
