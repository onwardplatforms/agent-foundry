"""Command-line interface for Agent Foundry."""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

import click
from dotenv import load_dotenv

from agent_foundry.agent import Agent
from agent_foundry.constants import AGENTS_DIR, DEFAULT_SYSTEM_PROMPT

# Load environment variables from .env file
load_dotenv()


def ensure_agents_dir() -> Path:
    """Ensure the agents directory exists."""
    agents_dir = Path(AGENTS_DIR)
    agents_dir.mkdir(exist_ok=True)
    return agents_dir


def load_agent(agent_id: str) -> Optional[Agent]:
    """Load an agent from its config file.

    Args:
        agent_id: The ID of the agent to load

    Returns:
        The loaded agent, or None if not found
    """
    agent_dir = Path(AGENTS_DIR) / agent_id
    config_file = agent_dir / "config.json"

    if not config_file.exists():
        return None

    with open(config_file) as f:
        config = json.load(f)

    return Agent(
        agent_id=config["id"],
        system_prompt=config["system_prompt"],
        model=config["model"],
        agent_dir=agent_dir,
    )


@click.group()
def cli() -> None:
    """Create and manage AI agents."""
    pass


@cli.command()
@click.argument("name", required=False)
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.option(
    "--system-prompt",
    help=f"Custom system prompt for the agent (default: {DEFAULT_SYSTEM_PROMPT})",
)
def create(name: Optional[str], debug: bool, system_prompt: Optional[str]) -> None:
    """Create a new agent.

    If no name is provided, generates a random ID.
    If no system prompt is provided, uses the default:
    "{DEFAULT_SYSTEM_PROMPT}"
    """
    if debug:
        click.echo("Debug mode enabled")

    # Ensure we have an agents directory
    agents_dir = ensure_agents_dir()

    # Generate or use provided agent ID
    agent_id = name or str(uuid.uuid4())[:8]
    agent_dir = agents_dir / agent_id

    if agent_dir.exists():
        click.echo(f"Error: Agent {agent_id} already exists")
        return

    # Create the agent
    agent = Agent.create(agent_id=agent_id, system_prompt=system_prompt)

    # Create agent directory
    agent_dir.mkdir(parents=True)

    # Save basic config
    config = {
        "id": agent_id,
        "model": agent.model,
        "system_prompt": agent.system_prompt,
    }

    with open(agent_dir / "config.json", "w") as f:
        json.dump(config, f, indent=2)

    click.echo(f"Created new agent: {agent_id}")
    click.echo(f"Configuration saved to: {agent_dir}/config.json")


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


async def _run_chat_session(agent: Agent) -> None:
    """Run an interactive chat session with an agent."""
    try:
        while True:
            # Get user input
            message = click.prompt("You", prompt_suffix=" > ")
            if message.lower() == "exit":
                break

            # Process message and get response
            click.echo("\nAgent > ", nl=False)  # Start agent response line
            await agent.chat(message)  # We don't need to capture the response
            click.echo("\n")  # Add newline after response

    except KeyboardInterrupt:
        click.echo("\nSession ended by user")
    except Exception as e:
        click.echo(f"\nError: {e}")
    finally:
        click.echo("\nSession ended")


@cli.command()
@click.argument("agent_id")
@click.option("--debug", is_flag=True, help="Enable debug mode")
def run(agent_id: str, debug: bool) -> None:
    """Run an interactive session with an agent."""
    if debug:
        click.echo("Debug mode enabled")

    # Load the agent
    agent = load_agent(agent_id)
    if not agent:
        click.echo(f"Error: Agent {agent_id} not found")
        return

    click.echo(f"Starting session with agent: {agent_id}")
    click.echo("Type 'exit' or press Ctrl+C to end the session")
    click.echo("Type your message and press Enter to send")
    click.echo("-" * 40)

    # Run the async chat session
    asyncio.run(_run_chat_session(agent))


@cli.command()
@click.option("--verbose", is_flag=True, help="Show detailed information")
def list(verbose: bool) -> None:
    """List all available agents."""
    agents_dir = ensure_agents_dir()

    click.echo("Available agents:")
    for agent_dir in agents_dir.iterdir():
        if agent_dir.is_dir():
            config_file = agent_dir / "config.json"
            if config_file.exists():
                with open(config_file) as f:
                    config = json.load(f)
                if verbose:
                    click.echo(f"  {agent_dir.name}:")
                    click.echo(f"    Model: {config['model']}")
                    click.echo(f"    System prompt: {config['system_prompt']}")
                else:
                    click.echo(f"  {agent_dir.name}")


@cli.command()
@click.argument("agent_id")
@click.option("--force", is_flag=True, help="Skip confirmation")
def delete(agent_id: str, force: bool) -> None:
    """Delete an agent."""
    agent_dir = Path(AGENTS_DIR) / agent_id

    if not agent_dir.exists():
        click.echo(f"Error: Agent {agent_id} not found")
        return

    if not force and not click.confirm(
        f"Are you sure you want to delete agent {agent_id}?"
    ):
        return

    import shutil

    shutil.rmtree(agent_dir)
    click.echo(f"Deleted agent: {agent_id}")


if __name__ == "__main__":
    cli()
