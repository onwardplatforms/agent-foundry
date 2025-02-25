"""Example script demonstrating plugin usage."""

import asyncio
import os
import logging
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

from agent_runtime_v2.config.types import AgentConfig, ModelConfig, PluginConfig
from agent_runtime_v2.conversation.context import Message, ConversationContext
from agent_runtime_v2.plugins.sources import LocalPluginSource
from agent_runtime_v2.agents.agent import Agent
from agent_runtime_v2.utils import configure_logging, LogLevel

# Load environment variables
load_dotenv()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Hello World Agent Example")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging"
    )
    parser.add_argument("--log-file", help="Log to a file in addition to console")
    parser.add_argument(
        "--agent-log-level",
        type=str,
        choices=["none", "debug", "info", "warning", "error", "critical"],
        default="none",
        help="Set the agent's log level (default: none - no logs)",
    )
    return parser.parse_args()


async def main():
    """Run the hello world example."""

    # Parse command line arguments
    args = parse_args()

    # Map the string log level to actual LogLevel value
    agent_log_level_map = {
        "none": LogLevel.NONE,
        "debug": LogLevel.DEBUG,
        "info": LogLevel.INFO,
        "warning": LogLevel.WARNING,
        "error": LogLevel.ERROR,
        "critical": LogLevel.CRITICAL,
    }
    agent_log_level = agent_log_level_map[args.agent_log_level]

    # Configure global logging based on verbosity
    log_level = LogLevel.DEBUG if args.verbose else LogLevel.NONE

    # Only enable specific loggers when in verbose mode
    specific_loggers = {}
    if args.verbose:
        specific_loggers = {
            "semantic_kernel.kernel": logging.INFO,
            "semantic_kernel.prompt_template.kernel_prompt_template": logging.INFO,
        }

    configure_logging(
        level=log_level,
        format_string="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        specific_loggers=specific_loggers,
        log_file=args.log_file,
    )

    logger = logging.getLogger(__name__)
    logger.info("Starting hello world example")

    if args.verbose:
        logger.debug("Verbose logging enabled")

    logger.info(f"Agent log level set to: {args.agent_log_level.upper()}")

    # Get the path to the hello plugin
    plugin_path = os.path.join(os.path.dirname(__file__), "hello_plugin")
    logger.debug(f"Plugin path: {plugin_path} (exists: {os.path.exists(plugin_path)})")

    # Create an agent config
    agent_config = AgentConfig(
        id="hello-agent",
        name="Hello Agent",
        description="An agent that demonstrates plugin usage",
        system_prompt="You are a friendly assistant that helps with greetings.",
        model=ModelConfig(provider="openai", model="gpt-4o", temperature=0.7),
        plugins=[
            PluginConfig(
                source=LocalPluginSource(path=Path(plugin_path)),
                # No variables needed for our simplified plugin
                variables={},
            )
        ],
        # Set the log level from command line argument
        log_level=agent_log_level,
    )
    logger.debug(f"Created agent config with log_level={args.agent_log_level.upper()}")

    # Create an agent instance
    agent = Agent(agent_config)
    logger.debug("Created agent instance")

    # Initialize the agent
    await agent.initialize()
    logger.info("Agent initialized")

    # Get the loaded plugins
    plugin_manager = agent.plugin_manager
    plugin_names = list(plugin_manager.plugins.keys())
    logger.info(f"Loaded plugins: {plugin_names}")

    # Get the hello plugin - plugin_manager.plugins returns a tuple of (plugin_class, plugin_instance)
    hello_plugin_tuple = plugin_manager.plugins.get("hello")
    if hello_plugin_tuple:
        _, hello_plugin = hello_plugin_tuple  # Unpack the tuple to get the instance
        logger.debug(
            f"Plugin hello loaded: class={hello_plugin.__class__.__name__}, instance={hello_plugin}"
        )

        # Get the kernel functions
        kernel_functions = hello_plugin.__class__.get_kernel_functions()
        logger.debug(f"Plugin kernel functions: {kernel_functions}")
    else:
        logger.error("Hello plugin not found")
        hello_plugin = None

    # Create a conversation context
    context = ConversationContext(conversation_id="test-conversation")
    logger.debug("Created conversation context")

    # Process user messages
    async def process_message(message_text):
        logger.info(f"Processing message: {message_text}")
        message = Message(content=message_text, role="user")

        try:
            async for response in agent.process_message(message, context):
                # In a real application, you would stream the response to the user
                # Here we just print it
                print(response, end="")
            print()  # Add a newline at the end
            logger.debug("Message processed")
        except Exception as e:
            logger.exception(f"Error processing message")
            print(f"\n\nError executing chat function: {e}")

    # Example conversation
    print("\nHello World Agent Example")
    print("-------------------------")
    print(f"Global log level: {'DEBUG' if args.verbose else 'NONE'}")
    print(f"Agent log level: {args.agent_log_level.upper()}")
    print("\nType 'exit' to quit.")
    print("Try asking for a greeting with or without a name.")
    user_input = input("\nUser: ")
    while user_input.lower() != "exit":
        await process_message(user_input)
        user_input = input("\nUser: ")


if __name__ == "__main__":
    # Ensure we have an API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Please set OPENAI_API_KEY environment variable")
        exit(1)

    # Run the example
    asyncio.run(main())
