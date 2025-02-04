"""Provider configuration for Agent Foundry."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Union


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

    def get_settings(self) -> ProviderSettings:
        """Get provider settings.

        Returns:
            Provider settings
        """
        settings = self.settings or {}
        temperature = settings.get("temperature", 0.7)

        provider_settings: Dict[ProviderType, Callable[[], ProviderSettings]] = {
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
