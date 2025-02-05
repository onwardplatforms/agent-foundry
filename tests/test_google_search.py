"""Tests for Google search capability."""

import os
from typing import Generator
from unittest.mock import patch

import pytest
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

from agent_foundry.capabilities.search.google import GoogleSearchCapability


@pytest.fixture
def mock_env_vars() -> Generator[None, None, None]:
    """Mock environment variables."""
    with patch.dict(
        os.environ,
        {
            "GOOGLE_API_KEY": "test-api-key",
            "GOOGLE_SEARCH_ENGINE_ID": "test-search-engine-id",
        },
    ):
        yield


@pytest.fixture
def kernel() -> Kernel:
    """Create a kernel with OpenAI chat service."""
    kernel = Kernel()
    kernel.add_service(
        OpenAIChatCompletion(
            service_id="chat-gpt",
            ai_model_id="gpt-3.5-turbo",
        )
    )
    return kernel


@pytest.mark.asyncio
async def test_google_search_initialization(
    mock_env_vars: None, kernel: Kernel
) -> None:
    """Test Google search capability initialization."""
    capability = GoogleSearchCapability()

    # Test properties
    assert capability.name == "GoogleSearch"
    assert "Google Custom Search API" in capability.description
    assert "Function: search" in capability.get_prompt_description()

    # Test initialization
    await capability.initialize(kernel=kernel)

    # Verify plugin was registered
    assert "WebSearch" in kernel.plugins

    # Test cleanup
    await capability.cleanup()
    assert capability._plugin is None


@pytest.mark.asyncio
async def test_google_search_missing_credentials(kernel: Kernel) -> None:
    """Test Google search capability with missing credentials."""
    capability = GoogleSearchCapability()

    with pytest.raises(ValueError, match="credentials not found"):
        await capability.initialize(kernel=kernel)


@pytest.mark.asyncio
async def test_google_search_missing_kernel() -> None:
    """Test Google search capability with missing kernel."""
    capability = GoogleSearchCapability()

    with pytest.raises(ValueError, match="Kernel is required"):
        await capability.initialize()
