"""Command-line interface for Agent Foundry."""

import uuid
from typing import Optional

import click


@click.group()
def cli() -> None:
    """Create and manage AI agents."""
    pass


@cli.command()
@click.argument("name", required=False)
@click.option("--debug", is_flag=True, help="Enable debug mode")
def create(name: Optional[str], debug: bool) -> None:
    """Create a new agent. If no name provided, generates a random ID."""
    agent_id = name or str(uuid.uuid4())[:8]
    if debug:
        click.echo("Debug mode enabled")
    click.echo(f"Creating new agent: {agent_id}")


@cli.command()
@click.argument("agent_id")
@click.option("--debug", is_flag=True, help="Enable debug mode")
def run(agent_id: str, debug: bool) -> None:
    """Run an interactive session with an agent."""
    if debug:
        click.echo("Debug mode enabled")
    click.echo(f"Starting session with agent: {agent_id}")


@cli.command()
@click.option("--verbose", is_flag=True, help="Show detailed information")
def list(verbose: bool) -> None:
    """List all available agents."""
    click.echo("Available agents:")
    # TODO: Implement agent listing logic


@cli.command()
@click.argument("agent_id")
@click.option("--force", is_flag=True, help="Skip confirmation")
def delete(agent_id: str, force: bool) -> None:
    """Delete an agent."""
    if not force and not click.confirm(
        f"Are you sure you want to delete agent {agent_id}?"
    ):
        return
    click.echo(f"Deleting agent: {agent_id}")


if __name__ == "__main__":
    cli()
