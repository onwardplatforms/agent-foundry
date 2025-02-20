"""Test configuration and shared fixtures."""

import os
import pytest
from typing import Dict, Any

from agent_runtime_v2.config.types import AgentConfig, ModelConfig
from agent_runtime_v2.errors import ErrorHandler, ErrorHandlerConfig, RetryConfig


@pytest.fixture
def mock_openai_key(monkeypatch):
    """Mock OpenAI API key for testing."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-123")


@pytest.fixture
def test_error_handler() -> ErrorHandler:
    """Create a test error handler with minimal retry config."""
    return ErrorHandler(
        config=ErrorHandlerConfig(
            retry_config=RetryConfig(
                max_attempts=2,
                initial_delay=0.1,
                max_delay=0.3,
                exponential_base=2.0,
                jitter=0.0,
            )
        )
    )


@pytest.fixture
def test_agent_config() -> AgentConfig:
    """Create a test agent configuration."""
    return AgentConfig(
        id="test_agent",
        name="Test Agent",
        description="Test agent for unit tests",
        system_prompt="You are a test assistant",
        model=ModelConfig(
            provider="openai", model_name="gpt-4", settings={"temperature": 0.7}
        ),
    )


@pytest.fixture
def test_conversation_id() -> str:
    """Get a test conversation ID."""
    return "test-conversation-123"
