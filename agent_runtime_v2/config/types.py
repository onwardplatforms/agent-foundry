from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path


@dataclass
class ModelConfig:
    """Configuration for a model provider"""

    provider: str
    model_name: str
    settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginConfig:
    """Configuration for a plugin"""

    name: str
    source: str
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityConfig:
    """Configuration for an agent capability"""

    type: str
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentConfig:
    """Configuration for an agent"""

    id: str
    name: str
    description: str
    system_prompt: str
    model: ModelConfig
    plugins: List[PluginConfig] = field(default_factory=list)
    capabilities: List[CapabilityConfig] = field(default_factory=list)


@dataclass
class ConversationConfig:
    """Configuration for a conversation"""

    id: str
    memory_enabled: bool = True
    memory_window: int = 10
    turn_strategy: str = "single_agent"  # or "round_robin", etc.
