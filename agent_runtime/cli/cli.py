"""Command-line interface for Agent Foundry with init-then-run and lockfile checks."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, cast

import click
from dotenv import load_dotenv

from agent_runtime.agent import Agent
from agent_runtime.plugins.manager import PluginConfig, PluginManager
from agent_runtime.validation import validate_agent_config

# Load environment from .env
load_dotenv()

LOCKFILE_NAME = "plugins.lock.json"


def set_debug_logging(debug: bool) -> None:
    """Set debug logging level."""
    if debug:
        logging.getLogger("agent_runtime").setLevel(logging.DEBUG)
        logging.getLogger("kernel").setLevel(logging.DEBUG)
        logging.getLogger(__name__).setLevel(logging.DEBUG)
        click.echo("Debug mode enabled - logging=DEBUG")
    else:
        logging.getLogger("agent_runtime").setLevel(logging.INFO)
        logging.getLogger("kernel").setLevel(logging.INFO)
        logging.getLogger(__name__).setLevel(logging.INFO)


def load_agent_config(config_path: Path) -> Dict[str, Any]:
    """Load and parse agent configuration from JSON."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return cast(Dict[str, Any], json.load(f))
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Invalid JSON in config file: {e}")
    except FileNotFoundError:
        raise click.ClickException(f"Config file not found: {config_path}")


@click.group()
@click.version_option()
@click.option("--debug", is_flag=True, help="Enable debug mode")
def cli(debug: bool) -> None:
    """CLI for managing AI agents."""
    set_debug_logging(debug)


@cli.command()
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
def validate(config_file: Path) -> None:
    """Validate an agent config file."""
    logger = logging.getLogger("agent_runtime")
    logger.debug("Validating config file: %s", config_file)

    is_valid, errors = validate_agent_config(config_file)
    if is_valid:
        click.echo("Configuration is valid.")
    else:
        click.echo("Configuration validation failed:")
        for err in errors:
            click.echo(f"  - {err}")
        exit(1)


@cli.command()
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
def init(config_file: Path) -> None:
    """Initialize an agent by installing plugins and updating the lockfile.

    Downloads and installs all required plugins, then updates the lockfile with their
    current state. This ensures reproducible agent environments.
    """
    logger = logging.getLogger("agent_runtime")
    logger.debug("Initializing agent from config: %s", config_file)

    is_valid, errors = validate_agent_config(config_file)
    if not is_valid:
        click.echo("Config validation failed:")
        for e in errors:
            click.echo(f"  - {e}")
        exit(1)

    cfg = load_agent_config(config_file)
    base_dir = config_file.parent
    lockfile = base_dir / LOCKFILE_NAME

    plugin_list = []
    for p in cfg.get("plugins", []):
        try:
            pc = PluginConfig(
                source=p["source"],
                version=p.get("version"),
                branch=p.get("branch"),
                variables=p.get("variables", {}),
            )
            plugin_list.append(pc)
        except (KeyError, ValueError) as ex:
            click.echo(f"Invalid plugin config: {ex}")
            exit(1)

    if not plugin_list:
        click.echo("No plugins found. Nothing to do.")
        exit(0)

    from semantic_kernel import Kernel

    kernel = Kernel()
    pm = PluginManager(kernel, base_dir)

    # Compare with existing lockfile
    old_lock_data = pm.read_lockfile(lockfile)
    if pm.compare_with_lock(plugin_list, old_lock_data):
        # Already up to date
        click.echo("Plugins are already up to date, no re-install needed.")
        # Optionally still load them so the user can do 'init' + 'run' without re-download
        for cfg_item in plugin_list:
            git_ref = cfg_item.git_ref if cfg_item.is_github_source else None
            pm.load_plugin(cfg_item.name, git_ref)
        click.echo("All plugins loaded from local cache.")
        # Done
        return

    # Otherwise, do the fresh install
    click.echo("Changes detected in plugin config or directory. Re-installing...")
    try:
        pm.install_and_load_plugins(
            plugin_list, lockfile=lockfile, force_reinstall=False
        )
        click.echo(f"Plugins installed successfully, lockfile updated: {LOCKFILE_NAME}")
    except Exception as e:
        logger.exception("Error installing plugins")
        click.echo(f"Failed to init plugins: {e}")
        exit(1)


def async_command(func: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Any]:
    """Decorator to run async commands with Click."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(func(*args, **kwargs))

    return wrapper


@async_command
async def _run_chat_session(agent: Agent) -> None:
    """Run an interactive chat session with the agent."""
    logger = logging.getLogger("agent_runtime")
    while True:
        try:
            message = click.prompt("You", prompt_suffix=" > ")
        except click.Abort:
            logger.info("User aborted.")
            break

        if message.lower() in ["exit", "quit"]:
            logger.debug("User requested exit.")
            break

        click.echo("\nAgent > ", nl=False)
        try:
            async for chunk in agent.chat(message):
                click.echo(chunk.content, nl=False)
        except Exception as e:
            logger.exception("Error in chat session.")
            click.echo(f"[Error: {e}]")
        click.echo("\n")


@cli.command()
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
def run(config_file: Path) -> None:
    """Run an interactive session with an agent.

    Ensures environment is in sync with lockfile, similar to 'terraform apply' or
    'terraform plan'. Verifies that all plugins are installed and up to date before
    starting the session.

    Args:
        config_file: Path to the agent configuration file
    """
    logger = logging.getLogger("agent_runtime")
    logger.debug("Running agent from config: %s", config_file)

    is_valid, errors = validate_agent_config(config_file)
    if not is_valid:
        click.echo("Config validation failed:")
        for e in errors:
            click.echo(f"  - {e}")
        exit(1)

    cfg = load_agent_config(config_file)
    base_dir = config_file.parent
    lockfile = base_dir / LOCKFILE_NAME

    # Build plugin configs for comparison
    plugin_list = []
    for p in cfg.get("plugins", []):
        try:
            pc = PluginConfig(
                source=p["source"],
                version=p.get("version"),
                branch=p.get("branch"),
                variables=p.get("variables", {}),
            )
            plugin_list.append(pc)
        except (KeyError, ValueError) as ex:
            click.echo(f"Invalid plugin config: {ex}")
            exit(1)

    from semantic_kernel import Kernel

    kernel = Kernel()
    pm = PluginManager(kernel, base_dir)

    # Check if lockfile is present
    if not lockfile.exists():
        click.echo("No lockfile found. Please run 'init' first.")
        exit(1)

    lock_data = pm.read_lockfile(lockfile)
    if not pm.compare_with_lock(plugin_list, lock_data):
        # If there's any mismatch, ask user to run init
        click.echo("Your plugin configuration has changed since last init.")
        click.echo("Please run 'init' again to update.")
        exit(1)

    # If we get here, environment is presumably correct: the user already did init
    # We only load the already-installed plugins from .plugins/ (no cloning).
    for cfg_item in plugin_list:
        try:
            git_ref = cfg_item.git_ref if cfg_item.is_github_source else None
            pm.load_plugin(cfg_item.name, git_ref)
        except Exception as e:
            logger.exception("Failed to load plugin '%s'.", cfg_item.name)
            click.echo(f"Plugin load failure for '{cfg_item.name}': {e}")
            exit(1)

    # Create agent with skip_init = True
    agent = Agent.from_config(cfg, base_dir=base_dir, skip_init=True)
    # Overwrite its kernel with our loaded kernel
    agent.kernel = kernel

    click.echo(f"Agent '{cfg['name']}' is ready.")
    click.echo("Type 'exit' or 'quit' to end the session.")
    click.echo("----------")

    _run_chat_session(agent)


if __name__ == "__main__":
    cli()
