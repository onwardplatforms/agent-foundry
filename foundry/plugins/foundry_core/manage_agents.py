"""Agent management functionality for the Foundry."""

import os
import shutil
from typing import List, Dict, Optional
import json

class AgentManager:
    def __init__(self):
        self.agents_dir = os.path.join(os.getcwd(), "agents")
        
    def list_agents(self) -> List[Dict[str, str]]:
        """List all available agents with their descriptions."""
        agents = []
        
        if not os.path.exists(self.agents_dir):
            return agents
            
        for agent_name in os.listdir(self.agents_dir):
            agent_path = os.path.join(self.agents_dir, agent_name)
            if not os.path.isdir(agent_path):
                continue
                
            config_path = os.path.join(agent_path, "agent.config.json")
            description = "No description available"
            
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                        description = config.get('description', description)
                except:
                    pass
                    
            agents.append({
                "name": agent_name,
                "description": description,
                "path": agent_path
            })
            
        return sorted(agents, key=lambda x: x['name'])
        
    def delete_agent(self, agent_name: str) -> bool:
        """Delete a specific agent by name."""
        agent_path = os.path.join(self.agents_dir, agent_name)
        
        if not os.path.exists(agent_path):
            return False
            
        try:
            shutil.rmtree(agent_path)
            return True
        except Exception:
            return False
            
    def delete_all_agents(self) -> List[str]:
        """Delete all agents and return list of deleted agent names."""
        deleted = []
        
        if not os.path.exists(self.agents_dir):
            return deleted
            
        for agent in self.list_agents():
            if self.delete_agent(agent['name']):
                deleted.append(agent['name'])
                
        return deleted 