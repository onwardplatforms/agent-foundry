import os
import click
from typing import Optional
from pathlib import Path
import shutil

class AgentCreator:
    def __init__(self):
        self.templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")
        
    def create_agent(self, name: str, template: str = "default") -> None:
        """Create a new agent with the given name using the specified template"""
        click.echo(f"Creating new agent '{name}' using template '{template}'...")
        
        # Ensure agents directory exists
        agents_dir = os.path.join(os.getcwd(), "agents")
        if not os.path.exists(agents_dir):
            os.makedirs(agents_dir)
            
        # Create agent directory inside agents directory
        agent_dir = os.path.join(agents_dir, name)
        if os.path.exists(agent_dir):
            click.echo(f"Error: Agent '{name}' already exists.", err=True)
            return
            
        os.makedirs(agent_dir)
        
        # Handle OpenAI API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            click.echo("OpenAI API key not found in environment variables.")
            if click.confirm("Would you like to set it now?", default=True):
                api_key = click.prompt("Please enter your OpenAI API key", type=str, hide_input=True)
            else:
                click.echo("Warning: Agent will not work without an API key.", err=True)
                api_key = "your-openai-api-key-here"
        
        # Get template directory
        template_dir = os.path.join(self.templates_dir, f"{template}_agent")
        if not os.path.exists(template_dir):
            click.echo(f"Error: Template '{template}' not found.", err=True)
            return
            
        # Create agent from template
        self._create_from_template(template_dir, agent_dir, {
            "agent_name": name.title(),
            "agent_name_lower": name.lower(),
            "class_name": name.replace("-", "_").title(),
            "openai_api_key": api_key
        })
        
        click.echo(f"✨ Agent '{name}' created successfully in agents/{name}/")
        click.echo("\nTo use this agent:")
        click.echo(f"1. cd agents/{name}")
        click.echo("2. Edit .env file with your OpenAI API key (if not already set)")
        click.echo(f"3. Run: foundry run {name}")
    
    def _create_from_template(self, template_dir: str, target_dir: str, replacements: dict) -> None:
        """Create files from templates with replacements"""
        for template_file in os.listdir(template_dir):
            if template_file.endswith(".template"):
                # Read template
                with open(os.path.join(template_dir, template_file), "r") as f:
                    content = f.read()
                
                # Apply replacements
                for key, value in replacements.items():
                    content = content.replace("{{" + key + "}}", value)
                
                # Write file (without .template extension)
                target_file = os.path.join(target_dir, template_file[:-9])
                with open(target_file, "w") as f:
                    f.write(content) 