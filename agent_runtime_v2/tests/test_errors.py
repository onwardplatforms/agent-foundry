"""Tests for the error handling system."""

import pytest
from datetime import datetime

from agent_runtime_v2.errors import (
    ErrorSeverity,
    ErrorContext,
    AgentRuntimeError,
    ModelError,
    RetryHandler,
    RetryConfig,
)


def test_error_severity_values():
    """Test that error severity enum has expected values."""
    assert ErrorSeverity.FATAL.value == "fatal"
    assert ErrorSeverity.CRITICAL.value == "critical"
    assert ErrorSeverity.ERROR.value == "error"
    assert ErrorSeverity.WARNING.value == "warning"
    assert ErrorSeverity.INFO.value == "info"


def test_error_context_creation():
    """Test creation of error context with various parameters."""
    # Basic context
    context = ErrorContext(component="test", operation="test_op")
    assert context.component == "test"
    assert context.operation == "test_op"
    assert context.details == {}
    assert context.trace_id is None

    # Context with details
    details = {"key": "value"}
    context = ErrorContext(
        component="test", operation="test_op", details=details, trace_id="trace-123"
    )
    assert context.details == details
    assert context.trace_id == "trace-123"


def test_agent_runtime_error_creation():
    """Test creation of base runtime error with various parameters."""
    context = ErrorContext("test", "test_op")
    error = AgentRuntimeError(
        message="Test error",
        severity=ErrorSeverity.ERROR,
        context=context,
        recovery_hint="Try again",
        cause=ValueError("Original error"),
    )

    assert str(error) == "Test error"
    assert error.severity == ErrorSeverity.ERROR
    assert error.context == context
    assert error.recovery_hint == "Try again"
    assert isinstance(error.cause, ValueError)

    # Test error dictionary conversion
    error_dict = error.to_dict()
    assert error_dict["message"] == "Test error"
    assert error_dict["severity"] == "error"
    assert error_dict["recovery_hint"] == "Try again"
    assert "Original error" in error_dict["cause"]


def test_model_error_defaults():
    """Test that model error uses correct defaults."""
    error = ModelError("Test model error")
    assert error.severity == ErrorSeverity.ERROR
    assert "Try again or use a different model" in error.recovery_hint


@pytest.mark.asyncio
async def test_retry_handler_success():
    """Test that retry handler succeeds after temporary failures."""
    retry_config = RetryConfig(
        max_attempts=3, initial_delay=0.1, max_delay=0.3, jitter=0
    )
    handler = RetryHandler(retry_config)
    context = ErrorContext("test", "test_op")

    # Counter for tracking attempts
    attempts = 0

    async def test_operation():
        nonlocal attempts
        attempts += 1
        if attempts < 2:  # Fail first attempt
            raise ValueError("Temporary error")
        return "success"

    result = await handler.retry(test_operation, context)
    assert result == "success"
    assert attempts == 2  # Should succeed on second attempt


@pytest.mark.asyncio
async def test_retry_handler_max_attempts():
    """Test that retry handler fails after max attempts."""
    retry_config = RetryConfig(
        max_attempts=2, initial_delay=0.1, max_delay=0.3, jitter=0
    )
    handler = RetryHandler(retry_config)
    context = ErrorContext("test", "test_op")

    async def failing_operation():
        raise ValueError("Persistent error")

    with pytest.raises(AgentRuntimeError) as exc_info:
        await handler.retry(failing_operation, context)

    assert "Operation failed after 2 attempts" in str(exc_info.value)
    assert exc_info.value.severity == ErrorSeverity.ERROR


@pytest.mark.asyncio
async def test_retry_handler_generator():
    """Test retry handler with async generator operations."""
    retry_config = RetryConfig(
        max_attempts=2, initial_delay=0.1, max_delay=0.3, jitter=0
    )
    handler = RetryHandler(retry_config)
    context = ErrorContext("test", "test_op")
    attempts = 0

    async def test_generator():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("First attempt fails")
        for i in range(3):
            yield str(i)

    results = []
    async for item in handler.retry_generator(test_generator, context):
        results.append(item)

    assert results == ["0", "1", "2"]
    assert attempts == 2  # Should succeed on second attempt
