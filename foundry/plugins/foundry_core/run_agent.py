import os
import sys
import subprocess
from typing import Optional

class AgentRunner:
    def __init__(self):
        self.base_path = os.path.join(os.path.dirname(__file__), '..', '..', '..')
        self.agents_path = os.path.join(self.base_path, 'agents')

    def get_agent_path(self, agent_name: str) -> str:
        """Get the full path for an agent directory"""
        return os.path.join(self.agents_path, agent_name)

    def verify_agent_exists(self, agent_name: str) -> bool:
        """Check if the agent exists"""
        agent_path = self.get_agent_path(agent_name)
        return os.path.exists(agent_path) and os.path.exists(os.path.join(agent_path, 'main.py'))

    def run_agent(self, agent_name: str) -> None:
        """Run the specified agent"""
        agent_path = self.get_agent_path(agent_name)
        
        if not self.verify_agent_exists(agent_name):
            raise ValueError(f"Agent '{agent_name}' not found or incomplete")
        
        # Get path to Python in the virtual environment
        if os.name == 'nt':  # Windows
            python_path = os.path.join(agent_path, 'venv', 'Scripts', 'python')
        else:  # Unix/Linux/Mac
            python_path = os.path.join(agent_path, 'venv', 'bin', 'python')
        
        if not os.path.exists(python_path):
            raise ValueError(f"Virtual environment not found for agent '{agent_name}'")
        
        # Run the agent using its virtual environment
        main_script = os.path.join(agent_path, 'main.py')
        subprocess.run([python_path, main_script], cwd=agent_path) 