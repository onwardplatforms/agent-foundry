# agent_runtime/core.py
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, AsyncIterator

from semantic_kernel import Kernel

from agent_runtime.config.hcl_loader import HCLConfigLoader
from agent_runtime.plugins.manager import PluginManager, PluginConfig
from agent_runtime.agent import Agent
from agent_runtime.validation import validate_agent_config

logger = logging.getLogger(__name__)


async def _chat_loop(agent: Agent) -> AsyncIterator[str]:
    """
    Yields the agent's responses chunk by chunk in an ongoing chat session.
    This is an internal helper for interactive modes or headless piping.
    """
    while True:
        # You could read from sys.stdin or do something else in a truly headless mode
        user_input = input("\nYou > ")
        if user_input.lower() in ["exit", "quit"]:
            logger.debug("User requested exit.")
            break

        # Produce agent response in streaming chunks
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
    Load HCL configs from the directory and perform validation checks.
    Returns the final dictionary of agent configurations.
    Raises exceptions if invalid or missing.
    """
    loader = HCLConfigLoader(str(config_dir))
    try:
        agent_configs = loader.load_config()
    except Exception as e:
        raise RuntimeError(f"Error loading configuration: {e}")

    if not agent_configs:
        raise RuntimeError("No agent configurations found in HCL files.")

    # Optionally run extra validation logic
    # E.g. validate_agent_config(agent_configs) if you want JSON schema checks
    # For now we skip or do minimal checks.
    return agent_configs


def collect_plugins_for_agents(
    agent_configs: Dict[str, Dict[str, Any]], agent_name: Optional[str] = None
) -> List[PluginConfig]:
    """
    Given all agent configs (from load_and_validate_config),
    return a list of all PluginConfig objects for either a single agent or all.
    """
    selected_agents = {}
    if agent_name:
        if agent_name not in agent_configs:
            raise ValueError(f"Agent '{agent_name}' not found in configuration.")
        selected_agents[agent_name] = agent_configs[agent_name]
    else:
        selected_agents = agent_configs

    all_plugins = []
    for name, cfg in selected_agents.items():
        plugins = cfg.get("plugins", [])
        for plugin_def in plugins:
            if (
                not isinstance(plugin_def, dict)
                or "type" not in plugin_def
                or "source" not in plugin_def
                or "name" not in plugin_def
            ):
                logger.warning("Skipping invalid plugin definition: %s", plugin_def)
                continue
            pc = PluginConfig(
                plugin_type=plugin_def["type"],
                name=plugin_def["name"],
                source=plugin_def["source"],
                version=plugin_def.get("version"),
                variables=plugin_def.get("variables", {}),
            )
            all_plugins.append(pc)

    return all_plugins


def init_plugins(config_dir: Path, agent_name: Optional[str] = None) -> None:
    """
    The 'init' step: load config, collect plugins, install them,
    and update the global lockfile. If agent_name is specified,
    only that agent's plugins are installed. Otherwise, all are installed.
    """
    agent_configs = load_and_validate_config(config_dir)
    plugin_list = collect_plugins_for_agents(agent_configs, agent_name)

    if not plugin_list:
        logger.info("No plugins found. Nothing to do.")
        return

    kernel = Kernel()
    pm = PluginManager(config_dir, kernel)

    # Compare with existing lock; if up-to-date, just load
    pm.plugin_configs.clear()
    for pc in plugin_list:
        pm.plugin_configs[pc.scoped_name] = pc

    if pm.compare_with_lock(plugin_list):
        print("All plugins are up to date.")
        # Load from local cache
        for cfg_item in plugin_list:
            git_ref = cfg_item.git_ref if cfg_item.is_github_source else None
            pm.load_plugin(cfg_item.scoped_name, git_ref)
        print("All plugins loaded from local cache.")
        return

    # Otherwise, install
    print("Installing plugins...")
    pm.install_and_load_plugins(plugin_list, force_reinstall=False)
    print("Plugins installed successfully; lockfile updated.")


def run_agent_interactive(config_dir: Path, agent_name: Optional[str] = None) -> None:
    """
    The 'run' step: load config, check lockfile, run chat in an interactive loop.
    If multiple agents exist and agent_name is None, picks the first.
    """
    agent_configs = load_and_validate_config(config_dir)

    # If multiple agents and user didn't pick one, pick the first by default
    if not agent_name:
        if len(agent_configs) > 1:
            raise ValueError(
                "Multiple agents found. Please specify which agent to run."
            )
        agent_name = list(agent_configs.keys())[0]

    if agent_name not in agent_configs:
        raise ValueError(f"Agent '{agent_name}' not found in configuration.")

    # Build the PluginManager & plugin configs
    agent_cfg = agent_configs[agent_name]
    plugin_list = collect_plugins_for_agents({agent_name: agent_cfg}, agent_name)
    kernel = Kernel()
    pm = PluginManager(config_dir, kernel)

    # Register plugin configs
    for pc in plugin_list:
        pm.plugin_configs[pc.scoped_name] = pc

    # Check lockfile for mismatches if we have remote plugins
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

    # Create the agent
    agent = Agent.from_config(agent_cfg, base_dir=config_dir, skip_init=True)
    agent.kernel = kernel

    print(f"Agent '{agent_cfg['name']}' is ready.")
    print("Type 'exit' or 'quit' to end the session.")
    print("----------")

    # Start the interactive chat loop
    import asyncio

    async def _interactive():
        while True:
            try:
                msg = input("You > ")
            except EOFError:
                break
            if msg.lower() in ["exit", "quit"]:
                break
            print("\nAgent > ", end="")
            try:
                async for chunk in agent.chat(msg):
                    print(chunk.content, end="", flush=True)
            except Exception as e:
                logger.exception("Error in chat session.")
                print(f"[Error: {e}]")
            print("\n")

    asyncio.run(_interactive())


def validate_configs_headless(config_dir: Path) -> None:
    """
    Simple 'validate' check without needing a full CLI prompt.
    Throws exception if validation fails.
    """
    # If you had a JSON schema or other checks, you could expand it here.
    load_and_validate_config(config_dir)
    # (Optional) do more checks or a separate schema validate
    print("Configuration is valid.")
