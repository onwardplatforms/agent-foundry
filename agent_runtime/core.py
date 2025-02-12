# agent_runtime/core.py

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, AsyncIterator

import click
from semantic_kernel import Kernel

from .config.hcl_loader import HCLConfigLoader
from .plugins.manager import PluginConfig, PluginManager
from .agent import Agent
from .cli.output import Style

logger = logging.getLogger(__name__)


async def _chat_loop(agent: Agent) -> AsyncIterator[str]:
    """
    Yields the agent's responses chunk by chunk in an ongoing chat session.
    This is an internal helper for interactive modes or headless piping.
    """
    while True:
        user_input = input("\nYou > ")
        if user_input.lower() in ["exit", "quit"]:
            logger.debug("User requested exit.")
            break

        print("\nAgent > ", end="", flush=True)
        try:
            async for chunk in agent.chat(user_input):
                yield chunk.content
        except Exception as e:
            logger.exception("Error in chat session.")
            print(f"[Error: {e}]")
            continue


def load_and_validate_config(config_dir: Path) -> Dict[str, Any]:
    """
    Load HCL configs from the directory and perform all validation checks.
    Returns the final dictionary of configurations including runtime, variables, models, plugins, and agents.
    Raises exceptions if invalid or missing.
    """
    loader = HCLConfigLoader(str(config_dir))
    try:
        config = loader.load_config()
    except Exception as e:
        # We re-raise as a RuntimeError so that the CLI can display them nicely.
        raise RuntimeError(f"Error loading configuration: {e}")

    if not config:
        raise RuntimeError("No configurations found in HCL files.")

    return config


def collect_plugins_for_agents(
    agent_configs: Dict[str, Dict[str, Any]], agent_name: Optional[str] = None
) -> List[PluginConfig]:
    """
    Given all agent configs (from load_and_validate_config),
    return a list of all PluginConfig objects for either a single agent or all.
    """
    all_plugins = {}

    # First collect all plugins from the raw configuration
    raw_plugins = agent_configs.get("plugin", {})
    for plugin_key, plugin_def in raw_plugins.items():
        plugin_type, plugin_name = plugin_key.split(":")
        pc = PluginConfig(
            plugin_type=plugin_type,
            name=plugin_name,
            source=plugin_def["source"],
            version=plugin_def.get("version"),
            variables=plugin_def.get("variables", {}),
        )
        all_plugins[plugin_key] = pc

    return list(all_plugins.values())


def init_plugins(config_dir: Path, agent_name: Optional[str] = None) -> None:
    """
    The 'init' step: load config, collect plugins, install them,
    and update the global lockfile. If agent_name is specified,
    only that agent's plugins are installed. Otherwise, all are installed.
    """
    from .plugins.manager import PluginManager

    config = load_and_validate_config(config_dir)
    plugin_list = collect_plugins_for_agents(config, agent_name)

    if not plugin_list:
        click.echo(Style.info("No plugins found. Nothing to do."))
        # Even with no plugins, we should update the lockfile to remove any previously locked plugins
        pm = PluginManager(config_dir, Kernel())
        new_data = pm.create_lock_data()
        pm.write_lockfile(config_dir / "plugins.lock.json", new_data)
        return

    kernel = Kernel()
    pm = PluginManager(config_dir, kernel)

    # Compare with existing lock
    pm.plugin_configs.clear()
    for pc in plugin_list:
        pm.plugin_configs[pc.scoped_name] = pc

    if pm.compare_with_lock(plugin_list):
        click.echo(Style.success("All plugins are up to date."))
        # Load from local cache
        for cfg_item in plugin_list:
            git_ref = cfg_item.git_ref if cfg_item.is_github_source else None
            pm.load_plugin(cfg_item.scoped_name, git_ref)
        click.echo(Style.success("All plugins loaded from local cache."))
        return

    pm.install_and_load_plugins(plugin_list, force_reinstall=False)
    click.echo(Style.success("Plugins installed successfully; lockfile updated."))


def run_agent_interactive(config_dir: Path, agent_name: Optional[str] = None) -> None:
    """
    The 'run' step: load config, check lockfile, run chat in an interactive loop.
    If multiple agents exist and agent_name is None, picks the first.
    """
    from .plugins.manager import PluginManager

    config = load_and_validate_config(config_dir)
    agent_configs = config["agent"]

    # If multiple agents and user didn't pick one, pick the first
    if not agent_name:
        if len(agent_configs) > 1:
            raise ValueError(
                "Multiple agents found. Please specify which agent to run."
            )
        agent_name = list(agent_configs.keys())[0]

    if agent_name not in agent_configs:
        raise ValueError(f"Agent '{agent_name}' not found in configuration.")

    agent_cfg = agent_configs[agent_name]
    plugin_list = collect_plugins_for_agents(config, agent_name)

    kernel = Kernel()
    pm = PluginManager(config_dir, kernel)

    # Compare with existing lock
    pm.plugin_configs.clear()
    for pc in plugin_list:
        pm.plugin_configs[pc.scoped_name] = pc

    # Check lockfile for remote plugins
    github_plugins = [p for p in plugin_list if p.is_github_source]
    if github_plugins:
        lockfile = config_dir / "plugins.lock.json"
        if not lockfile.exists():
            raise RuntimeError("No lockfile found. Please run 'init' first.")
        lock_data = pm.read_lockfile(lockfile)
        if not pm.compare_with_lock(plugin_list, lock_data):
            raise RuntimeError(
                "Your plugin configuration has changed since last init. "
                "Please run 'init' again to update."
            )

    # Load all the plugins
    for cfg_item in plugin_list:
        git_ref = cfg_item.git_ref if cfg_item.is_github_source else None
        pm.load_plugin(cfg_item.scoped_name, git_ref)

    # Create the Agent with our kernel that has the plugins loaded
    agent = Agent.from_config(agent_cfg, base_dir=config_dir, skip_init=True)
    agent.kernel = kernel

    click.echo(Style.success(f"Agent '{agent_cfg['name']}' is ready."))
    click.echo(Style.info("Type 'exit' or 'quit' to end the session."))
    click.echo(Style.info("Type 'reset' to start a new conversation."))
    click.echo("----------")

    import asyncio

    async def _interactive():
        while True:
            try:
                msg = input("\nYou > ")
            except EOFError:
                break

            if msg.lower() in ["exit", "quit"]:
                break
            elif msg.lower() == "reset":
                agent.start_new_session()
                click.echo(Style.info("Started new conversation"))
                continue

            print("\nAgent > ", end="")
            try:
                async for chunk in agent.chat(msg):
                    print(chunk.content, end="", flush=True)
            except Exception as e:
                logger.exception("Error in chat session.")
                print(Style.error(f"[Error: {e}]"))
            print("\n")

    asyncio.run(_interactive())
