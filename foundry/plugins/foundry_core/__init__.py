from typing import Dict, List, Optional

class FoundryCore:
    """Core functionality for the Agent Foundry"""
    
    def __init__(self):
        self.base_path = os.path.join(os.path.dirname(__file__), '..', '..', '..')
        self.agents_path = os.path.join(self.base_path, 'agents')
        
    def get_agent_path(self, agent_name: str) -> str:
        """Get the full path for an agent directory"""
        return os.path.join(self.agents_path, agent_name) 