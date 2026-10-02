"""Local plugin architecture for Elysia Phase 4."""

from app.services.plugins.base import PluginError, PluginManifest, PluginRecord, PluginToolAdapter
from app.services.plugins.manager import PluginManager, plugin_manager

__all__ = [
    "PluginError",
    "PluginManifest",
    "PluginRecord",
    "PluginToolAdapter",
    "PluginManager",
    "plugin_manager",
]
