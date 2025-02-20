"""
Error handling and recovery system for the agent runtime.
"""

import logging
import asyncio
import random
from typing import (
    Optional,
    Dict,
    Any,
    Callable,
    Awaitable,
    TypeVar,
    Generic,
    AsyncIterator,
    Union,
    AsyncGenerator,
)
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .types import AgentRuntimeError, ErrorSeverity, ErrorContext

# Type variables for generic error handling
T = TypeVar("T")
R = TypeVar("R")

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    initial_delay: float = 1.0  # seconds
    max_delay: float = 30.0  # seconds
    exponential_base: float = 2.0
    jitter: float = 0.1


def default_retry_config() -> RetryConfig:
    """Default retry configuration factory."""
    return RetryConfig()


@dataclass
class ErrorHandlerConfig:
    """Configuration for error handler."""

    retry_config: RetryConfig = field(default_factory=default_retry_config)
    error_callback: Optional[Callable[[AgentRuntimeError], Awaitable[None]]] = None
    recovery_callback: Optional[Callable[[AgentRuntimeError], Awaitable[bool]]] = None


class ErrorHandler:
    """Handles errors and implements recovery strategies."""

    def __init__(self, config: ErrorHandlerConfig):
        self.config = config
        self._error_counts: Dict[str, int] = {}
        self._last_errors: Dict[str, datetime] = {}

    async def handle_error(
        self, error: AgentRuntimeError, context_id: Optional[str] = None
    ) -> None:
        """Handle an error with appropriate logging and callbacks."""
        # Update error tracking
        if context_id:
            self._track_error(context_id)

        # Log error
        self._log_error(error)

        # Call error callback if configured
        if self.config.error_callback:
            try:
                await self.config.error_callback(error)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")

        # Attempt recovery if appropriate
        if error.severity != ErrorSeverity.FATAL:
            await self._attempt_recovery(error)

    async def _attempt_recovery(self, error: AgentRuntimeError) -> bool:
        """Attempt to recover from an error."""
        if not self.config.recovery_callback:
            return False

        try:
            return await self.config.recovery_callback(error)
        except Exception as e:
            logger.error(f"Error in recovery callback: {e}")
            return False

    def _track_error(self, context_id: str) -> None:
        """Track error occurrence for a context."""
        now = datetime.now()

        # Clean old errors
        self._clean_old_errors(now)

        # Update counts
        self._error_counts[context_id] = self._error_counts.get(context_id, 0) + 1
        self._last_errors[context_id] = now

    def _clean_old_errors(self, now: datetime) -> None:
        """Clean up old error tracking data."""
        threshold = now - timedelta(minutes=30)

        # Remove old entries
        self._error_counts = {
            k: v
            for k, v in self._error_counts.items()
            if self._last_errors.get(k, now) > threshold
        }
        self._last_errors = {
            k: v for k, v in self._last_errors.items() if v > threshold
        }

    def _log_error(self, error: AgentRuntimeError) -> None:
        """Log error with appropriate level and context."""
        log_level = self._get_log_level(error.severity)

        logger.log(
            log_level,
            f"{error.__class__.__name__}: {str(error)}",
            extra={
                "error_data": error.to_dict(),
                "timestamp": datetime.now().isoformat(),
            },
        )

    def _get_log_level(self, severity: ErrorSeverity) -> int:
        """Map error severity to logging level."""
        return {
            ErrorSeverity.FATAL: logging.CRITICAL,
            ErrorSeverity.CRITICAL: logging.ERROR,
            ErrorSeverity.ERROR: logging.WARNING,
            ErrorSeverity.WARNING: logging.INFO,
            ErrorSeverity.INFO: logging.DEBUG,
        }[severity]


class RetryHandler(Generic[T, R]):
    """Handles retrying operations with exponential backoff."""

    def __init__(self, config: RetryConfig):
        self.config = config

    async def retry_generator(
        self, operation: Callable[[], AsyncGenerator[R, None]], context: ErrorContext
    ) -> AsyncGenerator[R, None]:
        """Retry an async generator operation with exponential backoff."""
        last_error = None

        for attempt in range(self.config.max_attempts):
            try:
                async for item in operation():
                    yield item
                return
            except Exception as e:
                last_error = e

                if attempt + 1 < self.config.max_attempts:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Retry attempt {attempt + 1} failed, "
                        f"retrying in {delay:.2f}s",
                        extra={"context": context.__dict__},
                    )
                    await asyncio.sleep(delay)

        # If we get here, all retries failed
        raise AgentRuntimeError(
            f"Operation failed after {self.config.max_attempts} attempts",
            ErrorSeverity.ERROR,
            context,
            "Try again later",
            cause=last_error,
        )

    async def retry(
        self, operation: Callable[[], Awaitable[R]], context: ErrorContext
    ) -> R:
        """Retry an async operation with exponential backoff."""
        last_error = None

        for attempt in range(self.config.max_attempts):
            try:
                return await operation()
            except Exception as e:
                last_error = e

                if attempt + 1 < self.config.max_attempts:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Retry attempt {attempt + 1} failed, "
                        f"retrying in {delay:.2f}s",
                        extra={"context": context.__dict__},
                    )
                    await asyncio.sleep(delay)

        # If we get here, all retries failed
        raise AgentRuntimeError(
            f"Operation failed after {self.config.max_attempts} attempts",
            ErrorSeverity.ERROR,
            context,
            "Try again later",
            cause=last_error,
        )

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for next retry attempt."""
        delay = min(
            self.config.initial_delay * (self.config.exponential_base**attempt),
            self.config.max_delay,
        )

        # Add jitter
        jitter = delay * self.config.jitter
        return delay + (jitter * (2 * random.random() - 1))
