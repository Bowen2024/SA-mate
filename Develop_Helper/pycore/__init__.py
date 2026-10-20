"""
PyCore - 一个模块化、异步优先的 Python 后端框架。

核心模块：
- core: 配置、日志、异常、基础模式
- plugins: 带注册表的插件系统
- services: 带状态机的服务层
- execution: 流程执行和上下文管理
- api: FastAPI 集成
- integrations: 外部服务集成（LLM 等）
"""

__version__ = "0.1.0"

from pycore.core.config import ConfigManager, BaseSettings
from pycore.core.logger import Logger, LogLevel, LoggerConfig, get_logger
from pycore.core.exceptions import PyCoreError, ConfigurationError, PluginError, ServiceError
from pycore.core.schema import Result

__all__ = [
    # Version
    "__version__",
    # Config
    "ConfigManager",
    "BaseSettings",
    # Logger
    "Logger",
    "LogLevel",
    "LoggerConfig",
    "get_logger",
    # Exceptions
    "PyCoreError",
    "ConfigurationError",
    "PluginError",
    "ServiceError",
    # Schema
    "Result",
]
