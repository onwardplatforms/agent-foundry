import os
import json
import venv
import subprocess
from typing import Dict, List, Optional
from pathlib import Path
import semantic_kernel as sk
from semantic_kernel.contents import ChatHistory
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

class AgentCreator:
    def __init__(self):
        self.standard_plugins = ['web_search', 'read_write_code', 'grep_codebase']
        self.base_dependencies = ['semantic-kernel', 'python-dotenv']
    
    def create_agent_config(self, 
                          name: str, 
                          description: str,
                          plugins: List[str],
                          dependencies: List[str],
                          env_vars: List[str]) -> Dict:
        """Create the agent configuration dictionary"""
        return {
            "name": name,
            "description": description,
            "dependencies": self.base_dependencies + dependencies,
            "entry_module": "main.py",
            "plugins": plugins,
            "env_vars": env_vars
        }
    
    def setup_agent_directory(self, agent_path: str, config: Dict):
        """Set up the agent directory structure"""
        # Create directories
        os.makedirs(agent_path, exist_ok=True)
        os.makedirs(os.path.join(agent_path, 'plugins'), exist_ok=True)
        
        # Create virtual environment
        venv_path = os.path.join(agent_path, 'venv')
        venv.create(venv_path, with_pip=True)
        
        # Get path to pip in the new virtual environment
        if os.name == 'nt':  # Windows
            pip_path = os.path.join(venv_path, 'Scripts', 'pip')
        else:  # Unix/Linux/Mac
            pip_path = os.path.join(venv_path, 'bin', 'pip')
        
        # Install dependencies
        for dep in config['dependencies']:
            subprocess.run([pip_path, 'install', dep], check=True)
        
        # Write config file
        config_path = os.path.join(agent_path, 'agent.config.json')
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
            
        # Create .env file
        env_path = os.path.join(agent_path, '.env')
        with open(env_path, 'w') as f:
            f.write("OPENAI_API_KEY=\n")  # Always include OpenAI key
            for env_var in config['env_vars']:
                if env_var != "OPENAI_API_KEY":  # Avoid duplicates
                    f.write(f"{env_var}=\n")
        
        # Create main.py
        self.create_main_py(agent_path)

    def get_agent_path(self, agent_name: str) -> str:
        """Get the full path for an agent directory"""
        base_path = os.path.join(os.path.dirname(__file__), '..', '..', '..')
        return os.path.join(base_path, 'agents', agent_name)

    def create_main_py(self, agent_path: str):
        """Create the main entry point for the agent"""
        main_py_content = '''"""
Simple Chat Agent
"""
import os
from pathlib import Path
import semantic_kernel as sk
from semantic_kernel.contents import ChatHistory
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

def main():
    # Load environment variables from .env file
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        raise ValueError(f"No .env file found at {env_path}")
        
    # Load environment variables
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value
    
    # Initialize the kernel
    kernel = sk.Kernel()
    
    # Configure OpenAI chat completion
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in .env file")
        
    # Create chat completion service
    chat_service = OpenAIChatCompletion(
        ai_model_id="gpt-4-turbo-preview",
        api_key=api_key
    )
    kernel.add_service("chat", chat_service)
    
    # Initialize chat history
    chat_history = ChatHistory()
    chat_history.add_system_message(
        "You are a helpful AI assistant. You engage in natural conversation while helping users "
        "with their tasks. You maintain context of the conversation and provide relevant, accurate responses."
    )
    
    print("👋 Hello! I'm ready to chat. Type 'exit' to quit.")
    
    # Start interactive chat loop
    while True:
        try:
            user_input = input("You: ").strip()
            if user_input.lower() in ['exit', 'quit', 'bye']:
                print("👋 Goodbye!")
                break
                
            # Add user message to history
            chat_history.add_user_message(user_input)
            
            # Get response from the chat model
            result = kernel.invoke_chat(
                "chat",
                chat_history,
                settings={
                    "temperature": 0.7,
                    "top_p": 1.0,
                    "max_tokens": 1000,
                    "presence_penalty": 0.0,
                    "frequency_penalty": 0.0
                }
            )
            response_text = str(result).strip()
            
            # Add assistant's response to history
            chat_history.add_assistant_message(response_text)
            print(f"🤖 {response_text}")
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
'''
        
        with open(os.path.join(agent_path, 'main.py'), 'w') as f:
            f.write(main_py_content.lstrip()) 