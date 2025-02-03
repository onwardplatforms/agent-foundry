"""
Chat-Agent Agent
"""
import os
from typing import Optional, List
from pathlib import Path
import semantic_kernel as sk
from semantic_kernel.contents import ChatHistory
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

class Chat_AgentAgent:
    def __init__(self):
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
        
        # Initialize the semantic kernel
        self.kernel = sk.Kernel()
        
        # Configure OpenAI chat completion
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in .env file")
            
        # Create chat completion service
        chat_service = OpenAIChatCompletion(
            ai_model_id="gpt-4-turbo-preview",
            api_key=api_key
        )
        self.kernel.add_chat_service("chat", chat_service)
        
        # Initialize chat history
        self.chat_history = ChatHistory()
        
    async def chat(self, message: str) -> str:
        """Have a conversation with the agent"""
        # Add user message to history
        self.chat_history.add_user_message(message)
        
        # Get response from the chat model
        result = await self.kernel.invoke_chat(
            "chat",
            self.chat_history,
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
        self.chat_history.add_assistant_message(response_text)
        
        return response_text
        
    async def run(self, task: Optional[str] = None) -> None:
        """Run the agent with an optional task"""
        # Add system message to define agent behavior
        self.chat_history.add_system_message(
            "You are a helpful AI assistant. You engage in natural conversation while helping users "
            "with their tasks. You maintain context of the conversation and provide relevant, accurate responses."
        )
        
        if task:
            # If a task is provided, treat it as a chat message
            response = await self.chat(task)
            print(f"🤖 {response}")
        else:
            print("👋 Hello! I'm ready to chat. What can I help you with?")
            
            # Start interactive chat loop
            while True:
                try:
                    user_input = input("You: ").strip()
                    if user_input.lower() in ['exit', 'quit', 'bye']:
                        print("👋 Goodbye!")
                        break
                        
                    response = await self.chat(user_input)
                    print(f"🤖 {response}")
                    
                except KeyboardInterrupt:
                    print("\n👋 Goodbye!")
                    break 