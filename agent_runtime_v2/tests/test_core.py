"""Tests for core functionality."""

import os
import logging
import pytest

from agent_runtime_v2.core import configure_logging, get_error_handler


def test_logging_configuration_default(caplog):
    """Test that logging configuration uses WARNING level by default."""
    # Reset logging
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Configure logging with no environment variables
    if "LOG_LEVEL" in os.environ:
        del os.environ["LOG_LEVEL"]
    configure_logging()

    # Check default level
    assert logging.getLogger().getEffectiveLevel() == logging.WARNING

    # Verify HTTP logging is disabled by default
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() == logging.WARNING


def test_logging_configuration_custom(caplog, monkeypatch):
    """Test that logging configuration respects environment variables."""
    # Reset logging
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Set custom log level
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_HTTP_REQUESTS", "true")

    configure_logging()

    # Check custom level is applied
    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG

    # Verify HTTP logging is enabled
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.DEBUG
    assert logging.getLogger("httpcore").getEffectiveLevel() == logging.DEBUG


def test_logging_configuration_invalid_level(caplog):
    """Test that logging configuration handles invalid log levels gracefully."""
    # Reset logging
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Set invalid log level
    os.environ["LOG_LEVEL"] = "INVALID"
    configure_logging()

    # Should default to WARNING
    assert logging.getLogger().getEffectiveLevel() == logging.WARNING


def test_error_handler_singleton():
    """Test that error handler is a singleton instance."""
    handler1 = get_error_handler()
    handler2 = get_error_handler()

    assert handler1 is handler2  # Same instance

    # Check default configuration
    assert handler1.config.retry_config.max_attempts == 3
    assert handler1.config.retry_config.initial_delay == 1.0
    assert handler1.config.retry_config.max_delay == 30.0
