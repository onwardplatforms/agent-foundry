"""Interactive agent loop for CLI interaction."""

import asyncio
import click
import sys
import logging

from ..agents.agent import Agent
from ..conversation.context import Message, ConversationContext
from ..config.types import AgentConfig

logger = logging.getLogger(__name__)


async def _run_interactive_loop(agent_config: AgentConfig):
    """Run the interactive agent loop.

    Args:
        agent_config: Agent configuration
    """
    # Initialize agent
    logger.info(f"Initializing agent: {agent_config.name}")
    agent = Agent(agent_config)
    await agent.initialize()
    logger.info("Agent initialized successfully")

    # Create conversation context
    context = ConversationContext(conversation_id=f"cli-{agent_config.id}")
    logger.debug(f"Created conversation context with ID: {context.id}")

    # Welcome message
    click.echo(f"\n===== Agent: {agent_config.name} =====")
    click.echo("Type 'exit' to quit, or 'help' for more commands.")

    # Main loop
    while True:
        try:
            # Get user input
            user_input = click.prompt("\nYou", prompt_suffix="> ")
            logger.debug(f"User input: {user_input}")

            # Check for exit
            if user_input.lower() in ["exit", "quit"]:
                logger.info("User requested exit")
                break

            # Check for help
            if user_input.lower() == "help":
                click.echo("\nAvailable commands:")
                click.echo("  exit/quit - Exit the agent")
                click.echo("  help      - Show this help message")
                continue

            # Process message
            logger.info(f"Processing user message: {user_input[:50]}...")
            message = Message(content=user_input, role="user")

            # Display response
            click.echo("\nAssistant> ", nl=False)
            response_text = ""
            async for chunk in agent.process_message(message, context):
                click.echo(chunk, nl=False)
                response_text += chunk

            logger.debug(f"Agent response complete: {len(response_text)} chars")

        except KeyboardInterrupt:
            logger.info("User interrupted with Ctrl+C")
            click.echo("\nExiting...")
            break
        except Exception as e:
            logger.exception(f"Error in interactive loop: {e}")
            click.echo(f"\nError: {e}")


def interactive_loop(agent_config: AgentConfig):
    """Run the interactive agent loop (sync wrapper).

    Args:
        agent_config: Agent configuration
    """
    try:
        logger.info("Starting interactive loop")
        asyncio.run(_run_interactive_loop(agent_config))
        logger.info("Interactive loop completed")
    except KeyboardInterrupt:
        logger.info("Interactive loop interrupted")
        click.echo("\nExiting...")
    except Exception as e:
        logger.exception(f"Error in interactive loop: {e}")
        click.echo(f"\nError: {e}")
