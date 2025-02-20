"""
Core error types and base exceptions for the agent runtime.
"""

from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


class ErrorSeverity(Enum):
    """Severity levels for errors in the agent runtime."""

    FATAL = "fatal"  # System cannot continue
    CRITICAL = "critical"  # Feature/component cannot continue
    ERROR = "error"  # Operation failed but system can continue
    WARNING = "warning"  # Operation succeeded with issues
    INFO = "info"  # Informational message


@dataclass
class ErrorContext:
    """Context information for an error."""

    component: str
    operation: str
    details: Dict[str, Any] = field(default_factory=dict)
    trace_id: Optional[str] = None
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None


class AgentRuntimeError(Exception):
    """Base exception class for all agent runtime errors."""

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity,
        context: Optional[ErrorContext] = None,
        recovery_hint: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        self.severity = severity
        self.context = context
        self.recovery_hint = recovery_hint
        self.cause = cause
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary format."""
        return {
            "message": str(self),
            "severity": self.severity.value,
            "context": self.context.__dict__ if self.context else None,
            "recovery_hint": self.recovery_hint,
            "cause": str(self.cause) if self.cause else None,
        }


class ConfigurationError(AgentRuntimeError):
    """Raised when there is an error in configuration."""

    def __init__(
        self,
        message: str,
        context: Optional[ErrorContext] = None,
        recovery_hint: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            ErrorSeverity.CRITICAL,
            context,
            recovery_hint or "Check configuration values and format",
            cause,
        )


class AgentError(AgentRuntimeError):
    """Raised when there is an error in agent operations."""

    def __init__(
        self,
        message: str,
        context: Optional[ErrorContext] = None,
        recovery_hint: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            ErrorSeverity.ERROR,
            context,
            recovery_hint or "Check agent configuration and try again",
            cause,
        )


class PluginError(AgentRuntimeError):
    """Raised when there is an error with a plugin."""

    def __init__(
        self,
        message: str,
        context: Optional[ErrorContext] = None,
        recovery_hint: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            ErrorSeverity.ERROR,
            context,
            recovery_hint or "Check plugin configuration and dependencies",
            cause,
        )


class ModelError(AgentRuntimeError):
    """Raised when there is an error with a model provider."""

    def __init__(
        self,
        message: str,
        context: Optional[ErrorContext] = None,
        recovery_hint: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            ErrorSeverity.ERROR,
            context,
            recovery_hint or "Try again or use a different model",
            cause,
        )


class ConversationError(AgentRuntimeError):
    """Raised when there is an error in conversation processing."""

    def __init__(
        self,
        message: str,
        context: Optional[ErrorContext] = None,
        recovery_hint: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            ErrorSeverity.ERROR,
            context,
            recovery_hint or "Try restarting the conversation",
            cause,
        )


class SecurityError(AgentRuntimeError):
    """Raised when there is a security-related error."""

    def __init__(
        self,
        message: str,
        context: Optional[ErrorContext] = None,
        recovery_hint: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            ErrorSeverity.CRITICAL,
            context,
            recovery_hint or "Check security credentials and permissions",
            cause,
        )
