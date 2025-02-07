"""Provider registry for managing available providers."""

from typing import Dict, Optional, Type

from agent_runtime.providers.base import Provider, ProviderConfig, ProviderType
from agent_runtime.providers.ollama import OllamaProvider
from agent_runtime.providers.openai import OpenAIProvider


def get_provider(config: ProviderConfig) -> Provider:
    """Get a provider instance."""
    PROVIDERS = {
        ProviderType.OPENAI: OpenAIProvider,
        ProviderType.OLLAMA: OllamaProvider,
    }

    provider_class = PROVIDERS.get(config.name)
    if not provider_class:
        raise ValueError(f"Unsupported provider type: {config.name}")

    return provider_class(config)


def get_provider_config(config: dict, agent_id: Optional[str] = None) -> ProviderConfig:
    """Get provider configuration from agent config."""
    provider_data = config.get("provider")
    if not provider_data or not isinstance(provider_data, dict):
        raise ValueError("Provider configuration is required and must be a dictionary")

    return ProviderConfig.from_dict(provider_data, agent_id)
