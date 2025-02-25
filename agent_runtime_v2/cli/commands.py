"""CLI commands for agently.run."""

import click
import sys
import os
import logging
from pathlib import Path

from ..config.parser import load_agent_config
from ..utils import configure_logging, LogLevel
from .interactive import interactive_loop

logger = logging.getLogger(__name__)


@click.group()
def cli():
    """agently.run - Declarative AI agents without code."""
    pass


@cli.command()
@click.option(
    "--agent", "-a", default="agently.yaml", help="Path to agent configuration file"
)
@click.option(
    "--log-level",
    type=click.Choice(
        ["none", "debug", "info", "warning", "error", "critical"], case_sensitive=False
    ),
    help="Override the log level",
)
def run(agent, log_level):
    """Run an agent from your configuration."""
    # Set up logging
    if log_level:
        level = getattr(LogLevel, log_level.upper())
        configure_logging(level=level)
        logger.debug(f"Log level set to {log_level.upper()}")
    else:
        configure_logging(level=LogLevel.NONE)

    logger.info(f"Starting agently run with agent config: {agent}")

    # Load agent config
    try:
        agent_path = Path(agent)
        if not agent_path.exists():
            click.echo(f"Error: Agent configuration file not found: {agent_path}")
            sys.exit(1)

        agent_config = load_agent_config(agent_path)
        logger.info(f"Loaded agent configuration for: {agent_config.name}")

        # Check for required OpenAI API key if using OpenAI provider
        if agent_config.model.provider == "openai" and not os.environ.get(
            "OPENAI_API_KEY"
        ):
            click.echo("Error: OPENAI_API_KEY environment variable not set")
            click.echo("Please set it with: export OPENAI_API_KEY=your_key_here")
            sys.exit(1)

        # Run interactive loop
        interactive_loop(agent_config)
    except Exception as e:
        click.echo(f"Error: {e}")
        logger.exception(f"Error running agent: {e}")
        sys.exit(1)
