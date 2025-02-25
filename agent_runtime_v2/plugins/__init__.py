"""Plugin system for extending agent capabilities."""

from .base import Plugin, PluginVariable, VariableValidation
from .sources import PluginSource, LocalPluginSource, GitHubPluginSource
from .manager import PluginManager

__all__ = [
    "Plugin",
    "PluginVariable",
    "VariableValidation",
    "PluginSource",
    "LocalPluginSource",
    "GitHubPluginSource",
    "PluginManager",
]
