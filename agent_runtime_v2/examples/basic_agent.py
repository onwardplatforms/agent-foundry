"""
Basic example of using the agent runtime.

This example demonstrates:
- Basic agent initialization and interaction
- Error handling and retries
- Logging configuration
"""

import os
import logging
import asyncio
from dotenv import load_dotenv

from agent_runtime_v2 import (
    Agent,
    AgentConfig,
    ModelConfig,
    Message,
    ConversationContext,
)
from agent_runtime_v2.errors import ModelError

# Load environment variables
load_dotenv()

# Get a logger for this module
logger = logging.getLogger(__name__)


async def main():
    try:
        # Check for OpenAI API key
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY environment variable is not set")

        # Create agent configuration
        agent_config = AgentConfig(
            id="test_agent",
            name="Test Agent",
            description="A simple test agent",
            system_prompt="You are a helpful AI assistant. You maintain context of the conversation and can refer back to previous messages.",
            model=ModelConfig(
                provider="openai", model_name="gpt-4", settings={"temperature": 0.7}
            ),
        )

        # Initialize the agent
        agent = Agent(agent_config)
        await agent.initialize()
        logger.info("Agent initialized successfully")

        # Create conversation context
        context = ConversationContext("test_conversation")

        # Start interactive chat
        print("\nChat with the agent (Ctrl+C to exit)")
        print("--------------------------------------")

        while True:
            try:
                # Get user input
                user_input = input("\nYou: ")
                if not user_input.strip():
                    continue

                # Create message and log
                message = Message(content=user_input, role="user")
                logger.debug("Processing user input", extra={"input": user_input})

                # Process through agent
                print("\nAgent: ", end="", flush=True)
                async for response in agent.process_message(message, context):
                    print(response, end="", flush=True)
                print("\n")

            except KeyboardInterrupt:
                print("\nExiting chat...")
                break

            except ModelError as e:
                logger.error("Model error occurred", exc_info=e)
                print(f"\nError: {str(e)}")

            except Exception as e:
                logger.error("Unexpected error", exc_info=e)
                print(f"\nAn unexpected error occurred: {str(e)}")

    except Exception as e:
        logger.error("Failed to initialize agent", exc_info=e)
        print(f"Failed to initialize agent: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
