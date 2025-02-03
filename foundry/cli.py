import click
import os
import sys
import uuid
from typing import Optional
from dotenv import load_dotenv
from foundry.plugins.foundry_core.create_agent import AgentCreator
from foundry.plugins.foundry_core.run_agent import AgentRunner
from foundry.plugins.foundry_core.manage_agents import AgentManager

# Load foundry's environment variables
load_dotenv()

@click.group()
@click.option('--debug/--no-debug', default=False, help="Enable debug mode")
def cli(debug: bool):
    """Agent Foundry CLI - Create and manage AI agents"""
    # Verify OPENAI_API_KEY is set
    if not os.getenv('OPENAI_API_KEY'):
        click.echo("Warning: OPENAI_API_KEY not found in environment variables.", err=True)
        if not click.confirm("Would you like to set it now?"):
            click.echo("The foundry may not work correctly without an API key.", err=True)
            return
        
        api_key = click.prompt("Please enter your OpenAI API key", type=str, hide_input=True)
        with open('.env', 'w') as f:
            f.write(f"OPENAI_API_KEY={api_key}\n")
        os.environ['OPENAI_API_KEY'] = api_key
    
    if debug:
        # Set up debug logging
        pass

@cli.command()
@click.argument('agent_name', required=False)
def create(agent_name: Optional[str]):
    """Create a new agent through an interactive wizard"""
    creator = AgentCreator()
    
    # Start interactive wizard
    click.echo("Hello! Let's create a new agent.")
    
    # Generate random ID if name not provided
    if not agent_name:
        agent_name = f"chat-agent-{str(uuid.uuid4())[:8]}"
        click.echo(f"No name provided. Using generated ID: {agent_name}")
    
    # Get description
    description = click.prompt(
        "What's the main purpose of this agent?",
        default="A simple chat agent powered by GPT-4"
    )
    
    # For now, we'll keep it simple with just the chat capability
    plugins = []
    dependencies = []
    env_vars = ['OPENAI_API_KEY']
    
    # Show summary
    click.echo("\nHere's what we'll create:")
    click.echo(f"Name: {agent_name}")
    click.echo(f"Description: {description}")
    click.echo("Type: Simple Chat Agent")
    
    if not click.confirm("\nProceed with creation?", default=True):
        click.echo("Cancelled.")
        return
    
    # Create the agent
    try:
        config = creator.create_agent_config(
            name=agent_name,
            description=description,
            plugins=plugins,
            dependencies=dependencies,
            env_vars=env_vars
        )
        creator.setup_agent_directory(creator.get_agent_path(agent_name), config)
        
        # Use foundry's API key for the new agent
        foundry_api_key = os.getenv('OPENAI_API_KEY')
        env_path = os.path.join(creator.get_agent_path(agent_name), '.env')
        with open(env_path, 'w') as f:
            f.write(f"OPENAI_API_KEY={foundry_api_key}\n")
            
        click.echo(f"\nAgent '{agent_name}' created successfully!")
        
        if click.confirm("Would you like to run this agent now?"):
            ctx = click.get_current_context()
            ctx.invoke(run, agent_name=agent_name)
            
    except Exception as e:
        click.echo(f"Error creating agent: {str(e)}", err=True)
        sys.exit(1)

@cli.command()
@click.argument('agent_name')
def run(agent_name: str):
    """Run an existing agent"""
    runner = AgentRunner()
    
    try:
        runner.run_agent(agent_name)
    except Exception as e:
        click.echo(f"Error running agent: {str(e)}", err=True)
        sys.exit(1)

@cli.command()
def list():
    """List all available agents"""
    manager = AgentManager()
    agents = manager.list_agents()
    
    if not agents:
        click.echo("No agents found.")
        return
        
    click.echo("\nAvailable agents:")
    click.echo("-" * 50)
    
    for agent in agents:
        click.echo(f"\n{agent['name']}")
        click.echo(f"Description: {agent['description']}")
        
    click.echo(f"\nTotal agents: {len(agents)}")

@cli.command()
@click.argument('agent_name', required=False)
@click.option('--all', 'delete_all', is_flag=True, help="Delete all agents")
@click.option('--force/--no-force', default=False, help="Force deletion without confirmation")
def delete(agent_name: Optional[str], delete_all: bool, force: bool):
    """Delete an existing agent"""
    manager = AgentManager()
    
    if delete_all:
        if not force and not click.confirm("Are you sure you want to delete ALL agents?"):
            click.echo("Operation cancelled.")
            return
            
        deleted = manager.delete_all_agents()
        if deleted:
            click.echo(f"Successfully deleted {len(deleted)} agents:")
            for name in deleted:
                click.echo(f"  - {name}")
        else:
            click.echo("No agents to delete.")
        return
        
    if not agent_name:
        click.echo("Error: Please provide an agent name or use --all to delete all agents.", err=True)
        sys.exit(1)
        
    if not force and not click.confirm(f"Are you sure you want to delete agent '{agent_name}'?"):
        click.echo("Operation cancelled.")
        return
        
    if manager.delete_agent(agent_name):
        click.echo(f"Successfully deleted agent '{agent_name}'")
    else:
        click.echo(f"Error: Agent '{agent_name}' not found or could not be deleted.", err=True)
        sys.exit(1)

if __name__ == '__main__':
    cli() 