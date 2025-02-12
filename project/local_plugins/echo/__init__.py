"""Local test plugin package."""

from dataclasses import dataclass, fields, field
from typing import Optional, Any
from semantic_kernel.functions import kernel_function
import os
import logging

logger = logging.getLogger(__name__)


@dataclass
class PluginIO:
    """Base class for plugin inputs/outputs configuration."""

    description: str
    default: Optional[Any] = None
    required: bool = False
    sensitive: bool = False


@dataclass
class EchoPluginConfig:
    """Configuration for the Echo plugin."""

    signature: str = field(
        default="Anonymous",
        metadata={
            "description": "Signature to use for messages",
            "required": False,
            "sensitive": False,
        },
    )


class Plugin:
    """A test plugin with some basic functions."""

    config_class = EchoPluginConfig

    def __init__(self):
        """Initialize plugin with configuration."""
        self.config = self.config_class()
        # Load config values from environment variables
        for field in fields(self.config):
            field_name = field.name
            # First check for HCL-provided variables (set by plugin manager)
            env_var = f"AGENT_VAR_{field_name.upper()}"
            value = os.getenv(env_var)
            if value is not None:
                logger.debug(
                    "Loading config %s from HCL variable %s = %s",
                    field_name,
                    env_var,
                    value,
                )
                setattr(self.config, field_name, value)
            else:
                # Fallback to default value from config class
                default_value = getattr(self.config, field_name)
                logger.debug(
                    "Using default value for %s = %s", field_name, default_value
                )

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
        logger.debug("Using signature: %s", self.config.signature)
        return f"{message}\n\n(from local plugin)\n\nBest regards,\n{self.config.signature}"
