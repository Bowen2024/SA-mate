"""
Core module - Configuration, logging, exceptions, and base schemas.
"""

from pycore.core.exceptions import (
    PyCoreError,
    ConfigurationError,
    PluginError,
    ServiceError,
    ExecutionError,
    ValidationError,
)
from pycore.core.schema import Result
from pycore.core.config import ConfigManager, BaseSettings, ConfigLoader, TomlConfigLoader
from pycore.core.logger import Logger, LogLevel, LoggerConfig, get_logger

__all__ = [
    # Exceptions
    "PyCoreError",
    "ConfigurationError",
    "PluginError",
    "ServiceError",
    "ExecutionError",
    "ValidationError",
    # Schema
    "Result",
    # Config
    "ConfigManager",
    "BaseSettings",
    "ConfigLoader",
    "TomlConfigLoader",
    # Logger
    "Logger",
    "LogLevel",
    "LoggerConfig",
    "get_logger",
]
