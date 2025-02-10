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
from agent_runtime.config.hcl_loader import HCLConfigLoader

# Load environment from .env
load_dotenv()

LOCKFILE_NAME = "plugins.lock.json"
logger = logging.getLogger(__name__)


def set_debug_logging(debug: bool) -> None:
    """Set debug logging level."""
    # Configure root logger
    root_logger = logging.getLogger()
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    if debug:
        logging.getLogger("agent_runtime").setLevel(logging.DEBUG)
        logging.getLogger("kernel").setLevel(logging.DEBUG)
        logging.getLogger(__name__).setLevel(logging.DEBUG)
        click.echo("Debug mode enabled - logging=DEBUG")
    else:
        logging.getLogger("agent_runtime").setLevel(logging.INFO)
        logging.getLogger("kernel").setLevel(logging.INFO)
        logging.getLogger(__name__).setLevel(logging.INFO)


def load_agent_config(config_dir: Path) -> Dict[str, Any]:
    """Load and parse agent configuration from HCL files in directory."""
    try:
        loader = HCLConfigLoader(str(config_dir))
        return loader.load_config()
    except Exception as e:
        raise click.ClickException(f"Error loading configuration: {e}")


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
)
def validate(dir: Path) -> None:
    """Validate agent configuration in directory."""
    logger.debug("Validating config in directory: %s", dir)

    try:
        config = load_agent_config(dir)
        if not config:
            click.echo("No agent configurations found.")
            exit(1)
        click.echo("Configuration is valid.")
    except Exception as e:
        click.echo(f"Configuration validation failed: {e}")
        exit(1)


@cli.command()
@click.option(
    "--dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=".",
)
def init(dir: Path) -> None:
    """Initialize agents by installing plugins and updating the lockfile."""
    logger.debug("Initializing agents from directory: %s", dir)

    try:
        cfg = load_agent_config(dir)
        if not cfg:
            click.echo("No agent configurations found.")
            exit(1)
        logger.debug("Loaded agent configurations: %s", cfg)
    except Exception as e:
        click.echo(f"Failed to load configuration: {e}")
        exit(1)

    lockfile = dir / LOCKFILE_NAME

    # Process all agents
    for agent_name, agent_cfg in cfg.items():
        plugin_list = []
        logger.debug("Processing agent configuration: %s", agent_cfg)
        plugins = agent_cfg.get("plugins", [])
        logger.debug("Found plugins in agent config: %s", plugins)

        if not plugins:
            logger.debug("No plugins array found in agent config")
            click.echo(f"No plugins found for agent '{agent_name}'. Skipping.")
            continue

        for plugin in plugins:
            try:
                logger.debug(
                    "Processing plugin config: %s (type: %s)", plugin, type(plugin)
                )
                if not isinstance(plugin, dict):
                    logger.debug("Plugin config is not a dictionary")
                    continue

                if "source" not in plugin:
                    logger.debug("Plugin config missing 'source' field")
                    continue

                pc = PluginConfig(
                    source=plugin["source"],
                    version=plugin.get("version"),
                    branch=None,
                    variables=plugin.get("variables", {}),
                )
                logger.debug("Created plugin config: %s", pc)
                plugin_list.append(pc)
            except (KeyError, ValueError) as ex:
                logger.exception("Error processing plugin config")
                click.echo(f"Invalid plugin config in agent '{agent_name}': {ex}")
                exit(1)

        if not plugin_list:
            logger.debug("No valid plugins found after processing")
            click.echo(f"No plugins found for agent '{agent_name}'. Skipping.")
            continue

        from semantic_kernel import Kernel

        kernel = Kernel()
        pm = PluginManager(kernel, dir)

        # Compare with existing lockfile
        old_lock_data = pm.read_lockfile(lockfile)
        if pm.compare_with_lock(plugin_list, old_lock_data):
            click.echo(f"Plugins for agent '{agent_name}' are up to date.")
            for cfg_item in plugin_list:
                git_ref = cfg_item.git_ref if cfg_item.is_github_source else None
                pm.load_plugin(cfg_item.name, git_ref)
            click.echo("All plugins loaded from local cache.")
            continue

        click.echo(f"Installing plugins for agent '{agent_name}'...")
        try:
            pm.install_and_load_plugins(
                plugin_list, lockfile=lockfile, force_reinstall=False
            )
            click.echo(
                f"Plugins installed successfully, lockfile updated: {LOCKFILE_NAME}"
            )
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
@click.option(
    "--dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=".",
)
@click.option(
    "--agent",
    type=str,
    help="Name of the agent to run (required if multiple agents are configured)",
)
def run(dir: Path, agent: str) -> None:
    """Run an interactive session with an agent."""
    logger.debug("Running agent from directory: %s", dir)

    try:
        cfg = load_agent_config(dir)
        if not cfg:
            click.echo("No agent configurations found.")
            exit(1)
    except Exception as e:
        click.echo(f"Failed to load configuration: {e}")
        exit(1)

    # Select agent configuration
    if len(cfg) > 1 and not agent:
        click.echo(
            "Multiple agents found. Please specify which one to run with --agent"
        )
        click.echo("Available agents:")
        for name in cfg.keys():
            click.echo(f"  - {name}")
        exit(1)

    agent_name = agent or next(iter(cfg.keys()))
    if agent_name not in cfg:
        click.echo(f"Agent '{agent_name}' not found in configuration")
        exit(1)

    agent_cfg = cfg[agent_name]
    lockfile = dir / LOCKFILE_NAME

    # Build plugin configs
    plugin_list = []
    for plugin in agent_cfg.get("plugins", []):
        try:
            logger.debug("Processing plugin config: %s", plugin)
            pc = PluginConfig(
                source=plugin["source"],
                version=plugin.get("version"),
                branch=None,
                variables=plugin.get("variables", {}),
            )
            plugin_list.append(pc)
        except (KeyError, ValueError) as ex:
            click.echo(f"Invalid plugin config: {ex}")
            exit(1)

    from semantic_kernel import Kernel

    kernel = Kernel()
    pm = PluginManager(kernel, dir)

    # Check lockfile
    if not lockfile.exists():
        click.echo("No lockfile found. Please run 'init' first.")
        exit(1)

    lock_data = pm.read_lockfile(lockfile)
    if not pm.compare_with_lock(plugin_list, lock_data):
        click.echo("Your plugin configuration has changed since last init.")
        click.echo("Please run 'init' again to update.")
        exit(1)

    # Load plugins
    for cfg_item in plugin_list:
        try:
            git_ref = cfg_item.git_ref if cfg_item.is_github_source else None
            pm.load_plugin(cfg_item.name, git_ref)
        except Exception as e:
            logger.exception("Failed to load plugin '%s'.", cfg_item.name)
            click.echo(f"Plugin load failure for '{cfg_item.name}': {e}")
            exit(1)

    # Create agent
    agent = Agent.from_config(agent_cfg, base_dir=dir, skip_init=True)
    agent.kernel = kernel

    click.echo(f"Agent '{agent_cfg['name']}' is ready.")
    click.echo("Type 'exit' or 'quit' to end the session.")
    click.echo("----------")

    _run_chat_session(agent)


if __name__ == "__main__":
    cli()
