"""Base types and classes for providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterator, Dict, Optional, Union

from semantic_kernel.contents import ChatHistory, StreamingChatMessageContent


class ProviderType(str, Enum):
    """Provider types."""

    OPENAI = "openai"
    OLLAMA = "ollama"


@dataclass
class BaseProviderSettings:
    """Base provider settings."""

    temperature: float = 0.7


@dataclass
class OpenAISettings(BaseProviderSettings):
    """OpenAI provider settings."""

    top_p: float = 1.0
    max_tokens: int = 1000


@dataclass
class OllamaSettings(BaseProviderSettings):
    """Ollama provider settings."""

    base_url: str = "http://localhost:11434"


ProviderSettings = Union[BaseProviderSettings, OpenAISettings, OllamaSettings]


@dataclass
class ProviderConfig:
    """Provider configuration."""

    name: ProviderType
    model: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    agent_id: Optional[str] = None

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], agent_id: Optional[str] = None
    ) -> "ProviderConfig":
        """Create a provider config from a dictionary."""
        return cls(
            name=ProviderType(data["name"]),
            model=data.get("model"),
            settings=data.get("settings", {}),
            agent_id=agent_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert provider config to a dictionary."""
        return {
            "name": self.name.value,
            "model": self.model,
            "settings": self.settings or {},
        }

    def get_settings(self) -> ProviderSettings:
        """Get provider settings."""
        settings = self.settings or {}
        temperature = settings.get("temperature", 0.7)

        provider_settings = {
            ProviderType.OPENAI: lambda: OpenAISettings(
                temperature=temperature,
                top_p=settings.get("top_p", 1.0),
                max_tokens=settings.get("max_tokens", 1000),
            ),
            ProviderType.OLLAMA: lambda: OllamaSettings(
                temperature=temperature,
                base_url=settings.get("base_url", "http://localhost:11434"),
            ),
        }

        return provider_settings.get(
            self.name, lambda: BaseProviderSettings(temperature=temperature)
        )()


class Provider(ABC):
    """Abstract base class for providers."""

    def __init__(self, config: ProviderConfig):
        """Initialize the provider."""
        self.config = config
        self.settings: ProviderSettings = config.get_settings()
        self.agent_id = getattr(config, "agent_id", None)

    @abstractmethod
    def chat(self, history: ChatHistory) -> AsyncIterator[StreamingChatMessageContent]:
        """Process a chat message and return the response."""
        raise NotImplementedError  # pragma: no cover
