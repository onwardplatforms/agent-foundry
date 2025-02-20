from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any
from semantic_kernel.contents import ChatHistory

from ..core import get_error_handler
from ..errors import ModelError, ErrorContext, RetryHandler, RetryConfig


class ModelProvider(ABC):
    """Base class for model providers"""

    def __init__(self):
        self.error_handler = get_error_handler()
        self.retry_handler = RetryHandler(
            RetryConfig(max_attempts=3, initial_delay=1.0, max_delay=10.0)
        )

    @abstractmethod
    async def chat(self, history: ChatHistory, **kwargs) -> AsyncIterator[str]:
        """Process a chat message and return response chunks"""
        pass

    @abstractmethod
    async def get_embeddings(self, text: str) -> list[float]:
        """Get embeddings for text"""
        pass

    async def _handle_api_call(
        self, operation_name: str, **context_details
    ) -> ErrorContext:
        """Create error context for API calls"""
        return ErrorContext(
            component="model_provider",
            operation=operation_name,
            details=context_details,
        )

    def _create_model_error(
        self, message: str, context: ErrorContext, cause: Exception = None
    ) -> ModelError:
        """Create a standardized model error"""
        return ModelError(
            message=message,
            context=context,
            recovery_hint="Check API credentials and try again",
            cause=cause,
        )
