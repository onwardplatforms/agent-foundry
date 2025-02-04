"""Provider definitions for Agent Foundry."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class ProviderType(str, Enum):
    """Supported provider types."""

    OPENAI = "openai"
    OLLAMA = "ollama"


@dataclass
class BaseProviderSettings:
    """Base class for provider settings."""

    temperature: float = 0.7


@dataclass
class OpenAISettings(BaseProviderSettings):
    """Settings for OpenAI provider."""

    top_p: float = 0.95
    max_tokens: int = 1000


@dataclass
class OllamaSettings(BaseProviderSettings):
    """Settings for Ollama provider."""

    base_url: str = "http://localhost:11434"
    context_window: int = 4096


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
        """Create a provider config from a dictionary.

        Args:
            data: Dictionary containing provider configuration
            agent_id: Optional agent ID for environment variable handling

        Returns:
            A ProviderConfig instance
        """
        return cls(
            name=ProviderType(data["name"]),
            model=data.get("model"),
            settings=data.get("settings", {}),
            agent_id=agent_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert provider config to a dictionary.

        Returns:
            Dictionary representation of the provider config
        """
        return {
            "name": self.name.value,
            "model": self.model,
            "settings": self.settings or {},
        }

    def get_settings(self) -> BaseProviderSettings:
        """Get the appropriate settings class for this provider.

        Returns:
            Provider-specific settings instance
        """
        settings_dict = self.settings or {}

        if self.name == ProviderType.OPENAI:
            return OpenAISettings(**settings_dict)
        elif self.name == ProviderType.OLLAMA:
            return OllamaSettings(**settings_dict)
        else:
            raise ValueError(f"Unknown provider type: {self.name}")


def get_provider_config(
    config: Dict[str, Any], agent_id: Optional[str] = None
) -> ProviderConfig:
    """Get provider configuration from agent config.

    Args:
        config: Agent configuration dictionary
        agent_id: Optional agent ID for environment variable handling

    Returns:
        Provider configuration

    Raises:
        ValueError: If provider configuration is invalid
    """
    provider_data = config.get("provider")
    if not provider_data or not isinstance(provider_data, dict):
        raise ValueError("Provider configuration is required and must be a dictionary")

    return ProviderConfig.from_dict(provider_data, agent_id)
