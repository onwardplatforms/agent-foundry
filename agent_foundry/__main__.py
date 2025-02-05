"""Main entry point for the agent_foundry package."""

import logging

from semantic_kernel.utils.logging import setup_logging

from agent_foundry.cli.cli import cli
from agent_foundry.env import get_env_var


def main() -> None:
    """Entry point for the foundry CLI."""
    # Setup basic logging
    setup_logging()

    # Default log levels from environment
    log_level = get_env_var("AGENT_FOUNDRY_LOG_LEVEL", "INFO") or "INFO"
    kernel_log_level = get_env_var("AGENT_FOUNDRY_KERNEL_LOG_LEVEL", "INFO") or "INFO"

    # Configure loggers
    logging.getLogger("agent_foundry").setLevel(log_level)
    logging.getLogger("kernel").setLevel(kernel_log_level)

    # Run CLI
    cli()


if __name__ == "__main__":
    main()
