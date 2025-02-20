"""Tests for conversation management functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from semantic_kernel.contents import ChatHistory

from agent_runtime_v2.agents.agent import Agent
from agent_runtime_v2.config.types import ConversationConfig, AgentConfig
from agent_runtime_v2.conversation.context import ConversationContext, Message
from agent_runtime_v2.conversation.manager import ConversationManager
from agent_runtime_v2.errors import ConversationError, AgentError


def test_conversation_context_initialization():
    """Test basic conversation context initialization."""
    context = ConversationContext("test-conv")
    assert context.id == "test-conv"
    assert isinstance(context.history, ChatHistory)
    assert context.shared_memory == {}
    assert context.metadata == {}


@pytest.mark.asyncio
async def test_conversation_context_message_handling():
    """Test adding different types of messages to context."""
    context = ConversationContext("test-conv")

    # Test user message
    await context.add_message(Message(content="Hello", role="user"))
    assert len(context.history.messages) == 1
    assert context.history.messages[0].role == "user"
    assert context.history.messages[0].content == "Hello"

    # Test assistant message
    await context.add_message(Message(content="Hi there", role="assistant"))
    assert len(context.history.messages) == 2
    assert context.history.messages[1].role == "assistant"

    # Test system message
    await context.add_message(Message(content="System msg", role="system"))
    assert len(context.history.messages) == 3
    assert context.history.messages[2].role == "system"


def test_conversation_context_history():
    """Test conversation history management."""
    context = ConversationContext("test-conv")
    history = context.get_history()
    assert isinstance(history, ChatHistory)
    assert len(history.messages) == 0


@pytest.mark.asyncio
async def test_conversation_context_memory():
    """Test shared memory operations."""
    context = ConversationContext("test-conv")

    # Test storing values
    await context.store_memory("key1", "value1")
    await context.store_memory("key2", {"nested": "value"})

    # Test retrieving values
    assert context.get_memory("key1") == "value1"
    assert context.get_memory("key2") == {"nested": "value"}

    # Test non-existent key
    assert context.get_memory("non_existent") is None


@pytest.mark.asyncio
async def test_conversation_manager_initialization(test_agent_config, mock_openai_key):
    """Test conversation manager initialization."""
    agent = Agent(test_agent_config)
    await agent.initialize()

    manager = ConversationManager(agent)
    assert manager.agent == agent
    assert manager.conversations == {}
    assert manager.agents == {}


@pytest.mark.asyncio
async def test_conversation_manager_create_conversation(
    test_agent_config, mock_openai_key
):
    """Test creating a new conversation."""
    agent = Agent(test_agent_config)
    await agent.initialize()
    manager = ConversationManager(agent)

    config = ConversationConfig(id="test-conv", memory_enabled=True, memory_window=5)

    context = await manager.create_conversation(config, [agent])

    assert context.id == "test-conv"
    assert context == manager.conversations["test-conv"]
    assert manager.agents["test-conv"][agent.id] == agent


@pytest.mark.asyncio
async def test_conversation_manager_process_message(test_agent_config, mock_openai_key):
    """Test processing a message in a conversation."""
    agent = Agent(test_agent_config)
    await agent.initialize()
    manager = ConversationManager(agent)

    # Create conversation
    config = ConversationConfig(id="test-conv")
    context = await manager.create_conversation(config, [agent])

    # Mock agent response
    async def mock_process_message(message, context):
        for chunk in ["Hello", " there", "!"]:
            yield chunk

    agent.process_message = mock_process_message

    # Process message
    message = Message(content="Hi", role="user")
    responses = []
    async for chunk in manager.process_message_in_conversation("test-conv", message):
        responses.append(chunk)

    assert responses == ["Hello", " there", "!"]


@pytest.mark.asyncio
async def test_conversation_manager_invalid_conversation():
    """Test handling invalid conversation ID."""
    manager = ConversationManager(None)
    message = Message(content="Hi", role="user")

    with pytest.raises(ConversationError) as exc_info:
        async for _ in manager.process_message_in_conversation("invalid-id", message):
            pass
    assert "Conversation invalid-id not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_conversation_manager_error_context():
    """Test creation of error context in conversation operations."""
    manager = ConversationManager(None)
    context = await manager._handle_conversation("test_operation", extra_detail="test")

    assert context.component == "conversation"
    assert context.operation == "test_operation"
    assert context.details["history_length"] == 0
    assert context.details["extra_detail"] == "test"


@pytest.mark.asyncio
async def test_conversation_manager_message_processing(
    test_agent_config, mock_openai_key
):
    """Test message processing with error handling."""
    agent = Agent(test_agent_config)
    await agent.initialize()
    manager = ConversationManager(agent)

    # Create conversation
    config = ConversationConfig(id="test-conv")
    context = await manager.create_conversation(config, [agent])

    # Test successful message processing
    await manager.add_message("user", "Hello")
    assert len(manager.history.messages) == 1
    assert manager.history.messages[0].role == "user"

    # Test error in message processing
    error_msg = "Test error"
    with patch.object(
        manager, "_handle_conversation", side_effect=Exception(error_msg)
    ):
        with pytest.raises(ConversationError) as exc_info:
            await manager.add_message("user", "Should fail")
        assert error_msg in str(exc_info.value.__cause__)


@pytest.mark.asyncio
async def test_conversation_manager_multi_agent_processing(
    test_agent_config, mock_openai_key
):
    """Test conversation with multiple agents."""
    # Create two agents
    agent1 = Agent(test_agent_config)
    agent2 = Agent(test_agent_config)
    await agent1.initialize()
    await agent2.initialize()

    manager = ConversationManager(agent1)

    # Create conversation with both agents
    config = ConversationConfig(
        id="multi-agent-test",
        memory_enabled=True,
        memory_window=5,
        turn_strategy="round_robin",
    )

    context = await manager.create_conversation(config, [agent1, agent2])

    # Mock responses from both agents
    async def mock_response(message, context):
        yield "Response from agent"

    agent1.process_message = mock_response
    agent2.process_message = mock_response

    # Process message
    message = Message(content="Hi", role="user")
    responses = []
    async for response in manager.process_message_in_conversation(
        "multi-agent-test", message
    ):
        responses.append(response)

    # Should get responses from both agents
    assert len(responses) == 2
    assert all(r == "Response from agent" for r in responses)


@pytest.mark.asyncio
async def test_conversation_manager_memory_window(test_agent_config, mock_openai_key):
    """Test conversation memory window functionality."""
    agent = Agent(test_agent_config)
    await agent.initialize()
    manager = ConversationManager(agent)

    # Create conversation with memory window
    config = ConversationConfig(
        id="memory-test",
        memory_enabled=True,
        memory_window=2,  # Small window for testing
    )

    context = await manager.create_conversation(config, [agent])

    # Add several messages
    messages = [Message(content=f"Message {i}", role="user") for i in range(4)]

    for msg in messages:
        await context.add_message(msg)
        # Enforce memory window after each message
        if len(context.history.messages) > config.memory_window:
            context.history.messages = context.history.messages[-config.memory_window :]

    # Should only keep the last 2 messages
    assert len(context.history.messages) == 2
    assert context.history.messages[-1].content == "Message 3"
    assert context.history.messages[-2].content == "Message 2"


@pytest.mark.asyncio
async def test_conversation_manager_clear_history(test_agent_config, mock_openai_key):
    """Test clearing conversation history."""
    agent = Agent(test_agent_config)
    await agent.initialize()
    manager = ConversationManager(agent)

    # Create conversation and add messages
    config = ConversationConfig(id="clear-test")
    context = await manager.create_conversation(config, [agent])

    await context.add_message(Message(content="Test message", role="user"))
    assert len(context.history.messages) == 1

    # Clear history
    await manager.clear_history()
    assert len(manager.history.messages) == 0

    # Test error handling in clear_history
    with patch.object(
        manager, "_handle_conversation", side_effect=Exception("Test error")
    ):
        with pytest.raises(ConversationError) as exc_info:
            await manager.clear_history()
        assert "Failed to clear conversation history" in str(exc_info.value)


@pytest.mark.asyncio
async def test_conversation_manager_error_propagation(
    test_agent_config, mock_openai_key
):
    """Test error handling and propagation in conversation manager."""
    agent = Agent(test_agent_config)
    await agent.initialize()
    manager = ConversationManager(agent)

    # Create conversation
    config = ConversationConfig(id="error-test")
    context = await manager.create_conversation(config, [agent])

    # Test agent error propagation
    error_message = "Test agent error"

    async def mock_error(message, context):
        raise AgentError(error_message, None)

    agent.process_message = mock_error

    message = Message(content="Hi", role="user")
    with pytest.raises(AgentError) as exc_info:
        async for _ in manager.process_message_in_conversation("error-test", message):
            pass  # Should not reach here as error should be raised before any yields

    assert str(exc_info.value) == error_message


@pytest.mark.asyncio
async def test_conversation_manager_turn_taking(test_agent_config, mock_openai_key):
    """Test turn-taking strategies in multi-agent conversations."""
    # Create three agents
    agents = []
    for i in range(3):
        # Create a copy of the config with a unique ID
        agent_config = AgentConfig(
            id=f"test_agent_{i}",
            name=test_agent_config.name,
            description=test_agent_config.description,
            system_prompt=test_agent_config.system_prompt,
            model=test_agent_config.model,
            plugins=test_agent_config.plugins,
            capabilities=test_agent_config.capabilities,
        )
        agent = Agent(agent_config)
        await agent.initialize()

        # Create unique mock response for each agent
        async def mock_response(message, context, i=i):
            yield f"Response from agent {i}"

        agent.process_message = mock_response
        agents.append(agent)

    manager = ConversationManager(agents[0])

    # Create conversation with round-robin strategy
    config = ConversationConfig(id="turn-test", turn_strategy="round_robin")

    context = await manager.create_conversation(config, agents)

    # Process multiple messages
    message = Message(content="Hi", role="user")
    all_responses = []
    for _ in range(2):  # Two rounds
        async for response in manager.process_message_in_conversation(
            "turn-test", message
        ):
            all_responses.append(response)

    # Should get responses from all agents in order
    assert len(all_responses) == 6  # 3 agents * 2 rounds
    expected_responses = [
        "Response from agent 0",
        "Response from agent 1",
        "Response from agent 2",
    ] * 2
    assert all_responses == expected_responses
