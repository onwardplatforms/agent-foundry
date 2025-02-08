"""Command-line interface for Agent Runtime."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, cast

import click
from dotenv import load_dotenv

from agent_runtime.agent import Agent
from agent_runtime.validation import validate_agent_config

# Load environment variables from .env file
load_dotenv()


def set_debug_logging(debug: bool) -> None:
    """Set debug logging level if debug flag is True."""
    if debug:
        # Set debug logging for both our package and kernel
        logging.getLogger("agent_runtime").setLevel(logging.DEBUG)
        logging.getLogger("kernel").setLevel(logging.DEBUG)
        click.echo("Debug mode enabled - logging set to DEBUG level")


def load_agent_config(config_path: Path) -> Dict[Any, Any]:
    """Load and parse an agent configuration file.

    Args:
        config_path: Path to the agent configuration file

    Returns:
        The parsed configuration dictionary

    Raises:
        click.ClickException: If the file cannot be loaded or parsed
    """
    try:
        with open(config_path) as f:
            return cast(Dict[Any, Any], json.load(f))
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Invalid JSON in config file: {e}")
    except FileNotFoundError:
        raise click.ClickException(f"Config file not found: {config_path}")


@click.group()
@click.version_option()
@click.option("--debug", is_flag=True, help="Enable debug mode with verbose logging")
def cli(debug: bool) -> None:
    """Create and manage AI agents."""
    set_debug_logging(debug)


@cli.command()
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
def validate(config_file: Path) -> None:
    """Validate an agent configuration file.

    Args:
        config_file: Path to the agent configuration file
    """
    logger = logging.getLogger("agent_runtime")
    logger.debug("Validating config file: %s", config_file)

    # Validate the config
    is_valid, errors = validate_agent_config(config_file)

    if is_valid:
        click.echo("Configuration is valid!")
    else:
        click.echo("Configuration validation failed:")
        for error in errors:
            click.echo(f"  - {error}")
        exit(1)


@cli.command()
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
def init(config_file: Path) -> None:
    """Initialize an agent by downloading and setting up its plugins.

    Args:
        config_file: Path to the agent configuration file
    """
    logger = logging.getLogger("agent_runtime")
    logger.debug("Initializing agent from config: %s", config_file)

    # First validate the config
    is_valid, errors = validate_agent_config(config_file)
    if not errors:
        click.echo("Configuration is valid.")
    else:
        click.echo("Configuration validation failed:")
        for error in errors:
            click.echo(f"  - {error}")
        exit(1)

    # Create plugins directory next to config file
    plugins_dir = config_file.parent / "plugins"
    plugins_dir.mkdir(exist_ok=True)

    click.echo("\nInitialization complete! You can now run the agent.")


# Async wrapper for Click commands
def async_command(f: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Any]:
    """Wrap a coroutine to make it compatible with Click commands.

    Args:
        f: The coroutine function to wrap

    Returns:
        A synchronous function that runs the coroutine
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(f(*args, **kwargs))

    return wrapper


@async_command
async def _run_chat_session(agent: Agent) -> None:
    """Run an interactive chat session with an agent."""
    logger = logging.getLogger("agent_runtime")

    try:
        while True:
            # Get user input
            message = click.prompt("You", prompt_suffix=" > ")
            if message.lower() == "exit":
                logger.debug("User requested exit")
                break

            # Process message and get response
            logger.debug("Processing message: %s", message)
            click.echo("\nAgent > ", nl=False)  # Start agent response line
            async for chunk in agent.chat(message):
                click.echo(chunk.content, nl=False)
            click.echo("\n")  # Add newline after response

    except KeyboardInterrupt:
        logger.info("Session ended by user (KeyboardInterrupt)")
        click.echo("\nSession ended by user")
    except Exception as e:
        logger.exception("Error during chat session")
        click.echo(f"\nError: {e}")
    finally:
        logger.info("Chat session ended")
        click.echo("\nSession ended")


@cli.command()
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
def run(config_file: Path) -> None:
    """Run an interactive session with an agent defined in a config file.

    Args:
        config_file: Path to the agent configuration file
    """
    logger = logging.getLogger("agent_runtime")
    logger.debug("Starting agent from config: %s", config_file)

    # First validate the config
    is_valid, errors = validate_agent_config(config_file)
    if not errors:
        click.echo("Configuration is valid.")
    else:
        click.echo("Configuration validation failed:")
        for error in errors:
            click.echo(f"  - {error}")
        exit(1)

    # Load the config
    config = load_agent_config(config_file)

    # Create agent
    agent = Agent.from_config(config, config_file.parent)

    logger.info("Starting session with agent: %s", config["name"])
    click.echo(f"Starting session with agent: {config['name']}")
    click.echo("Type 'exit' or press Ctrl+C to end the session")
    click.echo("Type your message and press Enter to send")
    click.echo("-" * 40)

    # Run the async chat session
    _run_chat_session(agent)


if __name__ == "__main__":
    cli()
