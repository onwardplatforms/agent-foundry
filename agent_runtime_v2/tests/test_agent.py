"""Tests for the Agent class functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from semantic_kernel.contents import ChatHistory

from agent_runtime_v2.agents.agent import Agent
from agent_runtime_v2.conversation.context import Message, ConversationContext
from agent_runtime_v2.errors import AgentError


@pytest.mark.asyncio
async def test_agent_initialization(test_agent_config):
    """Test basic agent initialization."""
    agent = Agent(test_agent_config)
    assert agent.id == test_agent_config.id
    assert agent.name == test_agent_config.name
    assert agent.provider is None  # Provider not initialized yet


@pytest.mark.asyncio
async def test_agent_initialization_with_openai(test_agent_config, mock_openai_key):
    """Test agent initialization with OpenAI provider."""
    agent = Agent(test_agent_config)
    await agent.initialize()

    assert agent.provider is not None
    assert agent.provider.__class__.__name__ == "OpenAIProvider"


@pytest.mark.asyncio
async def test_agent_initialization_invalid_provider(test_agent_config):
    """Test agent initialization with invalid provider."""
    test_agent_config.model.provider = "invalid_provider"
    agent = Agent(test_agent_config)

    with pytest.raises(AgentError) as exc_info:
        await agent.initialize()

    assert "Failed to initialize agent" in str(exc_info.value)
    assert "Unsupported provider type" in str(exc_info.value.__cause__)


@pytest.mark.asyncio
async def test_agent_process_message(test_agent_config, mock_openai_key):
    """Test agent message processing."""
    agent = Agent(test_agent_config)
    await agent.initialize()

    # Mock the provider's chat method
    async def mock_chat(*args, **kwargs):
        for chunk in ["Hello", " there", "!"]:
            yield chunk

    agent.provider.chat = mock_chat

    # Create test message and context
    message = Message(content="Hi", role="user")
    context = ConversationContext("test-conv")

    # Process message
    responses = []
    async for chunk in agent.process_message(message, context):
        responses.append(chunk)

    assert responses == ["Hello", " there", "!"]
    assert len(context.history.messages) == 1


@pytest.mark.asyncio
async def test_agent_process_message_without_initialization(test_agent_config):
    """Test message processing without initialization."""
    agent = Agent(test_agent_config)
    message = Message(content="Hi", role="user")
    context = ConversationContext("test-conv")

    responses = []
    async for chunk in agent.process_message(message, context):
        responses.append(chunk)

    assert len(responses) == 1
    assert "Error processing message" in responses[0]
    assert "Try rephrasing your message or check agent status" in responses[0]


@pytest.mark.asyncio
async def test_agent_process_message_provider_error(test_agent_config, mock_openai_key):
    """Test handling of provider errors during message processing."""
    agent = Agent(test_agent_config)
    await agent.initialize()

    # Mock provider to raise an error
    async def mock_chat_error(*args, **kwargs):
        raise Exception("API Error")
        yield  # Need this to make it a valid async generator

    agent.provider.chat = mock_chat_error

    message = Message(content="Hi", role="user")
    context = ConversationContext("test-conv")

    responses = []
    async for chunk in agent.process_message(message, context):
        responses.append(chunk)

    assert len(responses) == 1
    assert "Error processing message" in responses[0]
    assert "Try rephrasing your message or check agent status" in responses[0]


@pytest.mark.asyncio
async def test_agent_error_context_creation(test_agent_config):
    """Test creation of error context in agent operations."""
    agent = Agent(test_agent_config)
    context = await agent._handle_agent_operation("test_operation", extra_detail="test")

    assert context.component == "agent"
    assert context.operation == "test_operation"
    assert context.details["agent_id"] == agent.id
    assert context.details["agent_name"] == agent.name
    assert context.details["extra_detail"] == "test"
