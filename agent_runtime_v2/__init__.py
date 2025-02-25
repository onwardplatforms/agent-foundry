"""Agent runtime v2 package."""

from .agents.agent import Agent
from .conversation.manager import ConversationManager
from .conversation.context import Message, ConversationContext
from .config.types import (
    AgentConfig,
    ModelConfig,
    PluginConfig,
    CapabilityConfig,
    ConversationConfig,
)
from .plugins.sources import (
    PluginSource,
    LocalPluginSource,
    GitHubPluginSource,
)
from .plugins.base import (
    Plugin,
    PluginVariable,
    VariableValidation,
)

__all__ = [
    # Core components
    "Agent",
    "ConversationManager",
    "Message",
    "ConversationContext",
    # Configuration
    "AgentConfig",
    "ModelConfig",
    "PluginConfig",
    "CapabilityConfig",
    "ConversationConfig",
    # Plugin system
    "Plugin",
    "PluginVariable",
    "VariableValidation",
    "PluginSource",
    "LocalPluginSource",
    "GitHubPluginSource",
]
