"""
Plugin system for PyCore.

Provides extensible plugin architecture with:
- Abstract base class for plugins
- Plugin registry for management
- Standardized result format
- Lifecycle hooks
"""

from pycore.plugins.base import BasePlugin, PluginResult
from pycore.plugins.registry import PluginRegistry

__all__ = [
    "BasePlugin",
    "PluginResult",
    "PluginRegistry",
]
