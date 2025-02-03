import os
import click
import importlib.util
from typing import Optional

class AgentRunner:
    def __init__(self):
        self.agents_dir = os.path.join(os.getcwd(), "agents")
        
    def run_agent(self, name: str, task: Optional[str] = None) -> None:
        """Run an agent with the given name and optional task"""
        click.echo(f"Starting agent '{name}'...")
        
        # Check if agents directory exists
        if not os.path.exists(self.agents_dir):
            click.echo("Error: No agents directory found. Create an agent first.", err=True)
            return
            
        # Check if agent exists
        agent_dir = os.path.join(self.agents_dir, name)
        if not os.path.exists(agent_dir):
            click.echo(f"Error: Agent '{name}' not found in agents directory.", err=True)
            return
            
        # Import agent module
        try:
            agent_path = os.path.join(agent_dir, "agent.py")
            spec = importlib.util.spec_from_file_location(f"{name}_agent", agent_path)
            if spec is None or spec.loader is None:
                click.echo(f"Error: Could not load agent module from {agent_path}", err=True)
                return
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Get agent class (convert name to valid Python class name)
            class_name = f"{name.replace('-', '_').title()}Agent"
            agent_class = getattr(module, class_name)
            agent = agent_class()
            
            # Run agent
            import asyncio
            asyncio.run(agent.run(task))
            
            click.echo(f"✨ Agent '{name}' completed successfully!")
            
        except Exception as e:
            click.echo(f"Error running agent: {str(e)}", err=True) 