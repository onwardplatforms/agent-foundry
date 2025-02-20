"""
Core functionality for the agent runtime.
"""

import os
import logging
from typing import Optional

from ..errors import ErrorHandler, ErrorHandlerConfig, RetryConfig


def configure_logging():
    """Configure logging based on environment variables."""
    # Get log level from environment (default to WARNING)
    log_level_str = os.getenv("LOG_LEVEL", "WARNING").upper()
    log_level = getattr(logging, log_level_str, logging.WARNING)

    # Get log format from environment (with default)
    log_format = os.getenv(
        "LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Configure root logger
    logging.basicConfig(level=log_level, format=log_format)

    # Configure HTTP request logging
    http_level = (
        log_level
        if os.getenv("LOG_HTTP_REQUESTS", "false").lower() == "true"
        else logging.WARNING
    )
    logging.getLogger("httpx").setLevel(http_level)
    logging.getLogger("httpcore").setLevel(http_level)

    # Log initial configuration at debug level
    logger = logging.getLogger(__name__)
    logger.debug(
        "Logging configured",
        extra={
            "log_level": log_level_str,
            "http_logging": os.getenv("LOG_HTTP_REQUESTS", "false"),
        },
    )


# Configure logging when module is imported
configure_logging()

# Global error handler instance
_error_handler: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """Get the global error handler instance."""
    global _error_handler
    if _error_handler is None:
        _error_handler = ErrorHandler(
            config=ErrorHandlerConfig(
                retry_config=RetryConfig(
                    max_attempts=3,
                    initial_delay=1.0,
                    max_delay=30.0,
                    exponential_base=2.0,
                    jitter=0.1,
                )
            )
        )
    return _error_handler


def set_error_handler(handler: ErrorHandler) -> None:
    """Set a custom error handler instance."""
    global _error_handler
    _error_handler = handler


__all__ = ["get_error_handler", "set_error_handler"]
