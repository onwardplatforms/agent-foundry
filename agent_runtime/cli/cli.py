# agent_runtime/cli/cli.py

"""Command-line interface for Agent Foundry with init-then-run and lockfile checks."""

import logging
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv

from agent_runtime.core import (
    load_and_validate_config,
    init_plugins,
    run_agent_interactive,
)
from agent_runtime.cli.output import Style

# Load environment from .env
load_dotenv()

logger = logging.getLogger(__name__)


def set_debug_logging(debug: bool) -> None:
    """Set debug logging level."""
    import sys

    # Configure root logger
    root_logger = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Configure specific loggers
    if debug:
        logging.getLogger("agent_runtime").setLevel(logging.DEBUG)
        logging.getLogger(__name__).setLevel(logging.DEBUG)
        logging.getLogger("httpx").setLevel(
            logging.INFO
        )  # Show HTTP requests in debug mode
        click.echo(Style.info("Debug mode enabled - logging=DEBUG"))
    else:
        logging.getLogger("agent_runtime").setLevel(logging.INFO)
        logging.getLogger(__name__).setLevel(logging.INFO)
        logging.getLogger("httpx").setLevel(
            logging.WARNING
        )  # Hide HTTP requests in normal mode


@click.group()
@click.version_option()
@click.option("--debug", is_flag=True, help="Enable debug mode")
def cli(debug: bool) -> None:
    """CLI for managing AI agents."""
    set_debug_logging(debug)


@cli.command()
@click.option(
    "--dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=".",
    help="Directory containing HCL config files",
)
def validate(dir: Path) -> None:
    """Validate agent configuration in directory."""
    logger.debug("Validating config in directory: %s", dir)

    try:
        click.echo(Style.header("Validating configuration..."))
        load_and_validate_config(dir)
        click.echo(Style.success("Configuration is valid."))
    except Exception as e:
        click.echo(Style.error(str(e)))
        raise SystemExit(1)


@cli.command()
@click.option(
    "--dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=".",
    help="Directory containing HCL config files",
)
@click.option(
    "--agent",
    type=str,
    help="Name of the agent to initialize (if not specified, all agents will be initialized)",
)
def init(dir: Path, agent: Optional[str] = None) -> None:
    """Initialize agents by installing plugins and updating the lockfile."""
    logger.debug("Initializing agents from directory: %s (agent=%s)", dir, agent)
    try:
        click.echo(Style.header("Initializing agent configuration..."))
        init_plugins(dir, agent)
    except Exception as e:
        logger.exception("Failed to init plugins.")
        click.echo(Style.error(f"Failed to init plugins: {e}"))
        raise SystemExit(1)


@cli.command()
@click.option(
    "--dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=".",
    help="Directory containing HCL config files",
)
@click.option(
    "--agent",
    type=str,
    help="Name of the agent to run (required if multiple agents are configured)",
)
def run(dir: Path, agent: Optional[str]) -> None:
    """Run an interactive session with an agent."""
    logger.debug("Running agent from directory: %s (agent=%s)", dir, agent)

    try:
        click.echo(Style.header("Starting agent..."))
        run_agent_interactive(dir, agent)
    except Exception as e:
        logger.exception("Error running agent.")
        click.echo(Style.error(str(e)))
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
