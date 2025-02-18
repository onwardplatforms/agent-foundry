# agent_runtime/core.py

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, AsyncIterator, Tuple

import click
from semantic_kernel import Kernel

from .schema.loader import ConfigLoader, VarLoader
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


def load_and_validate_config(
    config_dir: Path,
    var_files: Optional[Tuple[Path, ...]] = None,
    cli_vars: Optional[Tuple[str, ...]] = None,
) -> Dict[str, Any]:
    """Load and validate configuration from directory."""
    loader = ConfigLoader(config_dir)

    # Set up variable handling
    var_loader = VarLoader()

    # Load var files if provided
    if var_files:
        for var_file in var_files:
            var_loader.load_var_file(var_file)

    # Add CLI vars if provided
    if cli_vars:
        for var in cli_vars:
            var_loader.add_cli_var(var)

    # Load environment variables
    var_loader.load_env_vars()

    # Load config with our variable values
    return loader.load_config(var_loader=var_loader)


def collect_plugins_for_agents(
    agent_configs: Dict[str, Dict[str, Any]], agent_name: Optional[str] = None
) -> List[PluginConfig]:
    """
    Given all agent configs (from load_and_validate_config),
    return a list of all PluginConfig objects for either a single agent or all.
    """
    all_plugins = {}

    # First collect all plugins from the raw configuration
    # Note: HCL loader will only include non-commented blocks
    raw_plugins = agent_configs.get("plugin", {})
    logger.debug("Raw plugins from config: %s", raw_plugins)

    # If agent_name is specified, only collect plugins used by that agent
    if agent_name:
        agent_cfg = agent_configs.get("agent", {}).get(agent_name)
        if not agent_cfg:
            raise ValueError(f"Agent '{agent_name}' not found in configuration.")

        # Get the list of plugin references for this agent
        agent_plugins = agent_cfg.get("plugins", [])
        needed_plugins = set()

        # Collect the plugin keys that this agent needs
        for plugin_ref in agent_plugins:
            if isinstance(plugin_ref, str):
                # Handle ${plugin.type.name} references
                if plugin_ref.startswith("${plugin."):
                    parts = plugin_ref.strip("${").strip("}").split(".")
                    if len(parts) == 3:  # plugin.type.name
                        plugin_key = f"{parts[1]}:{parts[2]}"
                        needed_plugins.add(plugin_key)
            elif isinstance(plugin_ref, dict):
                # Handle inline plugin definitions
                plugin_type = plugin_ref.get("type")
                plugin_name = plugin_ref.get("name")
                if plugin_type and plugin_name:
                    plugin_key = f"{plugin_type}:{plugin_name}"
                    needed_plugins.add(plugin_key)

        logger.debug("Needed plugins for agent '%s': %s", agent_name, needed_plugins)
        # Only process plugins that this agent needs AND that exist in raw_plugins
        raw_plugins = {k: v for k, v in raw_plugins.items() if k in needed_plugins}
        logger.debug("Filtered plugins for agent '%s': %s", agent_name, raw_plugins)

    # Create PluginConfig objects for the needed plugins
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

    logger.debug(
        "Final plugin configs: %s", [p.scoped_name for p in all_plugins.values()]
    )
    return list(all_plugins.values())


def init_plugins(config_dir: Path, agent_name: Optional[str] = None) -> None:
    """
    The 'init' step: load config, collect plugins, install them,
    and update the global lockfile. If agent_name is specified,
    only that agent's plugins are installed. Otherwise, all are installed.
    """
    from .plugins.manager import PluginManager

    config = load_and_validate_config(config_dir)

    # First collect all plugins that should exist
    if agent_name:
        # If agent specified, only get plugins for that agent
        plugin_list = collect_plugins_for_agents(config, agent_name)
    else:
        # Otherwise get all plugins defined in the config
        plugin_list = collect_plugins_for_agents(config)

    kernel = Kernel()
    pm = PluginManager(config_dir, kernel)

    # Clear existing configs and store new ones using scoped names
    pm.plugin_configs.clear()
    for pc in plugin_list:
        pm.plugin_configs[pc.scoped_name] = pc

    # Create a new lockfile with just the current plugins
    logger.debug(
        "Creating new lockfile with plugins: %s", [p.scoped_name for p in plugin_list]
    )
    new_data = {"plugins": []}
    if plugin_list:
        new_data = pm.create_lock_data()

    if not plugin_list:
        click.echo(Style.info("No plugins found. Lockfile cleaned"))
        pm.write_lockfile(config_dir / "plugins.lock.json", new_data)
        return

    # Install and load plugins
    pm.install_and_load_plugins(plugin_list, force_reinstall=False)


def run_agent_interactive(
    config_dir: Path,
    agent_name: Optional[str] = None,
    var_files: Optional[Tuple[Path, ...]] = None,
    cli_vars: Optional[Tuple[str, ...]] = None,
) -> None:
    """Run an interactive session with an agent."""
    config = load_and_validate_config(config_dir, var_files, cli_vars)

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

        # Only compare the plugins that this agent needs
        if not pm.compare_with_lock(github_plugins, lock_data):
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
