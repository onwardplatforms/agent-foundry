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
from agent_runtime.utils import Style

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
        logging.getLogger("semantic_kernel").setLevel(logging.INFO)
        click.echo(Style.info("Debug mode enabled - logging=DEBUG"))
    else:
        logging.getLogger("agent_runtime").setLevel(logging.INFO)
        logging.getLogger(__name__).setLevel(logging.INFO)
        logging.getLogger("httpx").setLevel(
            logging.WARNING
        )  # Hide HTTP requests in normal mode
        logging.getLogger("semantic_kernel").setLevel(
            logging.WARNING
        )  # Silence SK logs
        # Explicitly silence specific SK loggers
        logging.getLogger("semantic_kernel.kernel").setLevel(logging.WARNING)
        logging.getLogger("semantic_kernel.connectors.ai").setLevel(logging.WARNING)
        logging.getLogger("semantic_kernel.functions").setLevel(logging.WARNING)


@click.group()
@click.version_option()
@click.option("--debug", is_flag=True, help="Enable debug mode")
def cli(debug: bool) -> None:
    """CLI for managing AI agents."""
    set_debug_logging(debug)


def _handle_validation_error(e: Exception, command_name: str) -> None:
    """Handle validation errors in a consistent way across commands."""
    error_msg = str(e)
    if "Configuration validation failed:" in error_msg:
        # Split into individual validation errors
        parts = error_msg.split("Configuration validation failed:")
        error_list = [err.strip() for err in parts[1].split("\n") if err.strip()]

        click.echo()  # Add newline before
        click.echo(Style.error(f"Error: Failed to {command_name}"))
        click.echo()
        click.echo("The configuration is invalid. The following errors were found:")
        click.echo()

        # Output each error with proper indentation and bullet points
        for err in error_list:
            click.echo(Style.error(f"  • {err}"))

        click.echo()  # Add newline after
    else:
        # For non-validation errors, use simpler format but try to extract block references
        click.echo()  # Add newline before
        click.echo(Style.error(f"Error: Failed to {command_name}"))
        click.echo()

        # Check if the error message contains a block reference
        if (
            "plugin." in error_msg
            or "model." in error_msg
            or "variable." in error_msg
            or "agent." in error_msg
        ):
            # The error already contains the block reference
            click.echo(f"  {error_msg}")
        else:
            # Try to infer context from the error message
            if "plugin" in error_msg.lower():
                click.echo("  In plugin configuration:")
            elif "model" in error_msg.lower():
                click.echo("  In model configuration:")
            elif "variable" in error_msg.lower():
                click.echo("  In variable configuration:")
            elif "agent" in error_msg.lower():
                click.echo("  In agent configuration:")
            click.echo(f"    {error_msg}")

        click.echo()


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
        click.echo()  # Add newline before
        click.echo(Style.header("Validating configuration..."))
        load_and_validate_config(dir)
        click.echo(Style.success("Configuration is valid."))
        click.echo()  # Add newline after
    except Exception as e:
        _handle_validation_error(e, "validate configuration")
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
        click.echo()  # Add newline before
        # First validate the configuration
        load_and_validate_config(dir)
        # Then initialize plugins if validation passes
        init_plugins(dir, agent)
        click.echo()  # Add newline after
    except Exception as e:
        _handle_validation_error(e, "initialize plugins")
        raise SystemExit(1)


@cli.command()
@click.option(
    "--dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=".",
    help="Directory containing HCL config files",
)
@click.option(
    "--var-file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    multiple=True,
    help="HCL variable file(s) to load",
)
@click.option(
    "--var",
    multiple=True,
    help="Individual variable values (format: 'name=value')",
)
@click.option(
    "--agent",
    type=str,
    help="Name of the agent to run (required if multiple agents are configured)",
)
def run(
    dir: Path, var_file: tuple[Path, ...], var: tuple[str, ...], agent: Optional[str]
) -> None:
    """Run an interactive session with an agent."""
    logger.debug("Running agent from directory: %s (agent=%s)", dir, agent)
    logger.debug("Variable files: %s", var_file)
    logger.debug("CLI variables: %s", var)

    try:
        click.echo()  # Add newline before
        click.echo(Style.header("Starting agent..."))
        run_agent_interactive(dir, agent, var_files=var_file, cli_vars=var)
        click.echo()  # Add newline after
    except Exception as e:
        logger.exception("Error running agent.")
        click.echo(Style.error(str(e)))
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
