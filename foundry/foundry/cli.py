import click
import os
import sys
from typing import Optional
from dotenv import load_dotenv
from foundry.plugins.foundry_core.create_agent import AgentCreator
from foundry.plugins.foundry_core.run_agent import AgentRunner

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
@click.argument('name')
@click.option('--template', '-t', default='default', help='Template to use for agent creation')
def create(name: str, template: str):
    """Create a new agent with the given name"""
    creator = AgentCreator()
    creator.create_agent(name, template)

@cli.command()
@click.argument('name')
@click.option('--task', '-t', help='Task for the agent to perform')
def run(name: str, task: Optional[str] = None):
    """Run an existing agent"""
    runner = AgentRunner()
    runner.run_agent(name, task)

if __name__ == '__main__':
    cli() 