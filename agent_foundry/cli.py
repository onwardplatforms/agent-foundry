"""Command line interface for Agent Foundry."""

import logging
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler

from agent_foundry.agent import Agent
from agent_foundry.config import AgentConfig
from agent_foundry.env import load_env_files
from agent_foundry.exceptions import AgentError

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=log_level,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger("agent_foundry")

# Create CLI app
app = typer.Typer()
agents_app = typer.Typer()
app.add_typer(agents_app, name="agents", help="Manage agents")

# Create console for rich output
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        from agent_foundry import __version__

        console.print(f"Agent Foundry CLI Version: {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Agent Foundry CLI."""


@agents_app.command("add")
def create_agent(
    agent_id: Optional[str] = typer.Argument(None, help="Agent ID"),
    capability: Optional[str] = typer.Option(
        None, "--capability", "-c", help="Add capability"
    ),
) -> None:
    """Create a new agent."""
    try:
        # Generate random ID if not provided
        if not agent_id:
            import uuid

            agent_id = str(uuid.uuid4())

        # Create agent config
        config = AgentConfig(agent_id=agent_id)
        if capability:
            config.capabilities.append(capability)

        # Create agent directory
        agent_dir = Path(".agents") / agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)

        # Save config
        config_path = agent_dir / "config.json"
        config.save(config_path)

        console.print(f"Created agent: {agent_id}")
        console.print(f"Configuration saved to: {config_path}")
        if capability:
            console.print(f"Added capability: {capability}")

    except Exception as e:
        console.print(f"[red]Error creating agent: {e}[/red]")
        raise typer.Exit(1)


@agents_app.command("remove")
def delete_agent(agent_id: str) -> None:
    """Delete an agent."""
    try:
        agent_dir = Path(".agents") / agent_id
        if not agent_dir.exists():
            console.print(f"[red]Agent not found: {agent_id}[/red]")
            raise typer.Exit(1)

        import shutil

        shutil.rmtree(agent_dir)
        console.print(f"Deleted agent: {agent_id}")

    except Exception as e:
        console.print(f"[red]Error deleting agent: {e}[/red]")
        raise typer.Exit(1)


@agents_app.command("list")
def list_agents() -> None:
    """List all agents."""
    try:
        agents_dir = Path(".agents")
        if not agents_dir.exists():
            console.print("No agents found")
            return

        agents = []
        for agent_dir in agents_dir.iterdir():
            if agent_dir.is_dir():
                config_path = agent_dir / "config.json"
                if config_path.exists():
                    config = AgentConfig.load(config_path)
                    agents.append(
                        {
                            "id": config.agent_id,
                            "capabilities": config.capabilities,
                        }
                    )

        if not agents:
            console.print("No agents found")
            return

        from rich.table import Table

        table = Table(title="Agents")
        table.add_column("ID", style="cyan")
        table.add_column("Capabilities", style="magenta")

        for agent in agents:
            table.add_row(
                agent["id"],
                ", ".join(agent["capabilities"]) if agent["capabilities"] else "None",
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error listing agents: {e}[/red]")
        raise typer.Exit(1)


@agents_app.command("run")
def run_agent(agent_id: str) -> None:
    """Run an agent."""
    try:
        # Load environment variables
        load_env_files(agent_id)

        # Create and run agent
        agent = Agent.from_config(agent_id)
        agent.run()

    except AgentError as e:
        console.print(f"[red]Error initializing agent: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error running agent: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
