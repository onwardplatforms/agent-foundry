"""
Simple Chat Agent
"""
import os
import asyncio
from pathlib import Path
import semantic_kernel as sk
from semantic_kernel.agents.open_ai import OpenAIAssistantAgent
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

AGENT_NAME = "ChatAgent"
AGENT_INSTRUCTIONS = """You are a helpful AI assistant. You engage in natural conversation while helping users 
with their tasks. You maintain context of the conversation and provide relevant, accurate responses."""

async def invoke_streaming_agent(agent: OpenAIAssistantAgent, thread_id: str, input: str) -> None:
    """Invoke the streaming agent with the user input."""
    await agent.add_chat_message(thread_id=thread_id, message=ChatMessageContent(role=AuthorRole.USER, content=input))

    first_chunk = True
    async for content in agent.invoke_stream(thread_id=thread_id):
        if content.role != AuthorRole.TOOL:
            if first_chunk:
                print(f"🤖 ", end="", flush=True)
                first_chunk = False
            print(content.content, end="", flush=True)
    print()

async def main():
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
    
    # Configure OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in .env file")
    
    # Initialize the kernel
    kernel = sk.Kernel()
    
    # Create the assistant agent
    agent = await OpenAIAssistantAgent.create(
        kernel=kernel,
        service_id="chat",
        name=AGENT_NAME,
        instructions=AGENT_INSTRUCTIONS,
        ai_model_id="gpt-4-turbo-preview"
    )
    
    # Create a thread for the conversation
    thread_id = await agent.create_thread()
    
    print("👋 Hello! I'm ready to chat. Type 'exit' to quit.")
    
    try:
        # Start interactive chat loop
        while True:
            try:
                user_input = input("You: ").strip()
                if user_input.lower() in ['exit', 'quit', 'bye']:
                    print("👋 Goodbye!")
                    break
                    
                await invoke_streaming_agent(agent, thread_id=thread_id, input=user_input)
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"Error: {str(e)}")
    finally:
        # Cleanup
        if agent is not None:
            await agent.delete_thread(thread_id)
            await agent.delete()

if __name__ == "__main__":
    asyncio.run(main())
