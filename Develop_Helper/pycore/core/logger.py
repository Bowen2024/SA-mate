"""
PyCore 日志系统。

基于 loguru 提供统一的日志接口，包括：
- 环境感知格式化（生产环境使用 JSON，开发环境使用彩色）
- 多输出目标（控制台、文件）
- 结构化日志支持
- 上下文注入
"""

import os
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from loguru import logger as loguru_logger


class LogLevel(str, Enum):
    """日志级别。"""

    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LoggerConfig:
    """日志器配置。"""

    def __init__(
        self,
        level: LogLevel = LogLevel.INFO,
        log_dir: Optional[Path | str] = None,
        console_enabled: bool = True,
        file_enabled: bool = True,
        json_format: bool = False,
        rotation: str = "1 day",
        retention: str = "30 days",
        compression: str = "zip",
        app_name: str = "pycore",
    ):
        self.level = level
        self.log_dir = Path(log_dir) if log_dir else Path("logs")
        self.console_enabled = console_enabled
        self.file_enabled = file_enabled
        self.json_format = json_format
        self.rotation = rotation
        self.retention = retention
        self.compression = compression
        self.app_name = app_name


class Logger:
    """
    统一的日志门面。

    用法：
        # 在应用启动时配置一次
        logger = Logger.configure(LoggerConfig(level=LogLevel.DEBUG))

        # 使用日志器
        logger.info("Application started", user_id=123)

        # 在任何地方获取日志器
        logger = get_logger()
        logger.debug("Processing request")

        # 创建带上下文的绑定日志器
        request_logger = logger.bind(request_id="abc123")
        request_logger.info("Handling request")
    """

    _instance: Optional["Logger"] = None

    def __init__(self, config: Optional[LoggerConfig] = None):
        self._config = config or LoggerConfig()
        self._logger = loguru_logger
        self._configured = False

    def _setup(self) -> None:
        """使用指定的处理器配置 loguru。"""
        if self._configured:
            return

        self._logger.remove()  # 移除默认处理器

        # 确定环境模式
        env_mode = os.getenv("ENV_MODE", "LOCAL").upper()
        is_production = env_mode in ("PROD", "PRODUCTION")
        use_json = is_production or self._config.json_format

        # 控制台格式
        if use_json:
            console_format = "{message}"
        else:
            console_format = (
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            )

        # 添加控制台处理器
        if self._config.console_enabled:
            self._logger.add(
                sys.stderr,
                level=self._config.level.value,
                format=console_format,
                serialize=use_json,
                colorize=not use_json,
            )

        # 添加文件处理器
        if self._config.file_enabled:
            self._config.log_dir.mkdir(parents=True, exist_ok=True)
            log_file = (
                self._config.log_dir
                / f"{self._config.app_name}_{datetime.now():%Y%m%d}.log"
            )
            self._logger.add(
                log_file,
                level=self._config.level.value,
                rotation=self._config.rotation,
                retention=self._config.retention,
                compression=self._config.compression,
                serialize=True,  # 文件始终使用 JSON
                encoding="utf-8",
            )

        self._configured = True

    @classmethod
    def configure(cls, config: Optional[LoggerConfig] = None) -> "Logger":
        """配置并返回日志器实例。"""
        if cls._instance is None:
            cls._instance = cls(config)
        cls._instance._setup()
        return cls._instance

    @classmethod
    def get(cls) -> "Logger":
        """获取日志器实例，如需要则使用默认配置。"""
        if cls._instance is None:
            return cls.configure()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置日志器实例（用于测试）。"""
        if cls._instance:
            cls._instance._logger.remove()
        cls._instance = None

    # 支持结构化数据的日志方法
    def trace(self, message: str, **kwargs: Any) -> None:
        """记录 trace 级别消息。"""
        self._log("TRACE", message, **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        """记录 debug 级别消息。"""
        self._log("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """记录 info 级别消息。"""
        self._log("INFO", message, **kwargs)

    def success(self, message: str, **kwargs: Any) -> None:
        """记录 success 级别消息。"""
        self._log("SUCCESS", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """记录 warning 级别消息。"""
        self._log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """记录 error 级别消息。"""
        self._log("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """记录 critical 级别消息。"""
        self._log("CRITICAL", message, **kwargs)

    def exception(self, message: str, **kwargs: Any) -> None:
        """记录异常及堆栈跟踪。"""
        self._logger.opt(depth=2, exception=True).error(
            self._format_message(message, **kwargs)
        )

    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        """内部日志方法。"""
        self._logger.opt(depth=2).log(level, self._format_message(message, **kwargs))

    def _format_message(self, message: str, **kwargs: Any) -> str:
        """格式化带额外上下文的消息。"""
        if kwargs:
            extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
            return f"{message} | {extra}"
        return message

    def bind(self, **kwargs: Any) -> "Logger":
        """创建带上下文的绑定日志器。"""
        bound = Logger.__new__(Logger)
        bound._logger = self._logger.bind(**kwargs)
        bound._config = self._config
        bound._configured = self._configured
        return bound

    def opt(
        self,
        *,
        exception: Optional[bool] = None,
        record: bool = False,
        lazy: bool = False,
        depth: int = 0,
    ) -> "Logger":
        """获取带选项的优化日志器。"""
        opt_logger = Logger.__new__(Logger)
        opt_logger._logger = self._logger.opt(
            exception=exception,
            record=record,
            lazy=lazy,
            depth=depth + 1,
        )
        opt_logger._config = self._config
        opt_logger._configured = self._configured
        return opt_logger


# 便捷函数
def get_logger() -> Logger:
    """获取全局日志器实例。"""
    return Logger.get()


def configure_logging(config: Optional[LoggerConfig] = None) -> Logger:
    """配置全局日志器。"""
    return Logger.configure(config)
