"""
PyCore 配置系统。

提供线程安全、类型安全的配置管理，支持 TOML 和 dotenv 文件，不继承进程环境。
"""

import json
import threading
import tomllib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

from pycore.core.exceptions import ConfigurationError

T = TypeVar("T", bound=BaseModel)


class BaseSettings(BaseModel):
    """
    所有设置组的基础类。

    用法：
        class AppSettings(BaseSettings):
            debug: bool = False
            host: str = "localhost"
            port: int = 8000
    """

    class Config:
        extra = "ignore"  # 忽略未知字段
        frozen = False  # 允许创建后修改
        validate_default = True


class ConfigLoader(ABC):
    """抽象配置加载器。"""

    @abstractmethod
    def load(self, path: Path) -> dict[str, Any]:
        """从源加载配置。"""

    @abstractmethod
    def supports(self, path: Path) -> bool:
        """检查此加载器是否支持给定路径。"""


class TomlConfigLoader(ConfigLoader):
    """使用 Python 3.11+ tomllib 的 TOML 配置加载器。"""

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in (".toml",)

    def load(self, path: Path) -> dict[str, Any]:
        try:
            with path.open("rb") as f:
                return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigurationError(
                f"Failed to parse TOML: {e}",
                config_path=str(path),
            )
        except FileNotFoundError:
            raise ConfigurationError(
                f"Configuration file not found: {path}",
                config_path=str(path),
            )


class DotEnvConfigLoader(ConfigLoader):
    """读取 dotenv 文件；不插值变量、不访问或写入进程环境。"""

    def supports(self, path: Path) -> bool:
        return path.name == ".env" or path.name.startswith(".env.") or path.suffix == ".env"

    def load(self, path: Path) -> dict[str, Any]:
        # 仅 dotenv 文件需要该依赖，TOML 调用保持可用。
        try:
            from dotenv.parser import parse_stream
        except ImportError:
            raise ConfigurationError(
                "Install python-dotenv>=1,<2 in the project environment",
                config_path=str(path),
            ) from None
        result: dict[str, Any] = {}
        try:
            with path.open(encoding="utf-8-sig") as stream:
                for binding in parse_stream(stream):
                    if binding.error or (binding.key is not None and binding.value is None):
                        raise ConfigurationError(
                            f"Invalid dotenv entry at line {binding.original.line}",
                            config_path=str(path),
                        )
                    if binding.key is None:
                        continue
                    key = binding.key.lower()
                    if key in result:
                        raise ConfigurationError(
                            f"Duplicate dotenv key at line {binding.original.line}",
                            config_path=str(path),
                        )
                    value = binding.value
                    # 集合使用 JSON；标量仍由设置模型校验，保留字符串前导零。
                    if value.lstrip().startswith(("[", "{")):
                        try:
                            value = json.loads(value)
                        except ValueError:
                            pass
                    result[key] = value
        except (OSError, UnicodeError):
            raise ConfigurationError("Cannot read dotenv file", config_path=str(path)) from None
        return result


class ConfigManager(Generic[T]):
    """
    线程安全的配置管理器，使用单例模式。

    用法：
        class AppSettings(BaseSettings):
            debug: bool = False
            database_url: str

        # 初始化
        config = ConfigManager[AppSettings]()
        config.load(AppSettings, "config/app.toml")

        # 访问设置
        print(config.settings.debug)

        # 或使用单例
        config = ConfigManager.instance()
    """

    _instance: Optional["ConfigManager"] = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not ConfigManager._initialized:
            with ConfigManager._lock:
                if not ConfigManager._initialized:
                    self._settings: Optional[T] = None
                    self._raw_config: dict[str, Any] = {}
                    self._loaders: list[ConfigLoader] = [
                        TomlConfigLoader(),
                        DotEnvConfigLoader(),
                    ]
                    self._config_path: Optional[Path] = None
                    ConfigManager._initialized = True

    @classmethod
    def instance(cls) -> "ConfigManager[T]":
        """获取单例实例。"""
        return cls()

    @classmethod
    def reset(cls) -> None:
        """重置单例实例（用于测试）。"""
        with cls._lock:
            cls._instance = None
            cls._initialized = False

    def register_loader(self, loader: ConfigLoader) -> "ConfigManager[T]":
        """注册自定义配置加载器。"""
        self._loaders.append(loader)
        return self

    def load(
        self,
        settings_class: type[T],
        config_path: str | Path,
        *,
        profile: Optional[str] = None,
        use_env: bool = False,
    ) -> "ConfigManager[T]":
        """
        从文件加载配置。

        参数：
            settings_class: 设置的 Pydantic 模型类
            config_path: 配置文件路径
            profile: 可选的配置文件名称（例如 'dev', 'prod'）
            use_env: 仅保留兼容参数；传 True 会报错，禁止进程环境覆盖
        """
        path = Path(config_path)
        if use_env:
            raise ConfigurationError(
                "Process environment overrides are disabled; use a configuration file",
                config_path=str(path),
            )

        # 查找合适的加载器
        loader = self._find_loader(path)
        if not loader:
            raise ConfigurationError(
                f"No loader available for file type: {path.suffix}",
                config_path=str(path),
            )

        # 加载原始配置
        self._raw_config = loader.load(path)
        self._config_path = path

        # 处理配置文件（例如 [dev], [prod]）
        config_data = self._apply_profile(self._raw_config, profile)

        # 创建设置实例
        try:
            self._settings = settings_class(**config_data)
        except Exception:
            raise ConfigurationError(
                "Failed to validate configuration against the settings model",
                config_path=str(path),
            ) from None

        return self

    def load_from_dict(
        self,
        settings_class: type[T],
        config_dict: dict[str, Any],
    ) -> "ConfigManager[T]":
        """从字典加载配置。"""
        try:
            self._settings = settings_class(**config_dict)
            self._raw_config = config_dict
        except Exception:
            raise ConfigurationError("Failed to validate configuration against the settings model") from None
        return self

    @property
    def settings(self) -> T:
        """获取已加载的设置。"""
        if self._settings is None:
            raise ConfigurationError("Configuration not loaded. Call load() first.")
        return self._settings

    @property
    def raw(self) -> dict[str, Any]:
        """获取原始配置字典。"""
        return self._raw_config

    def get(self, key: str, default: Any = None) -> Any:
        """通过键获取原始配置值。"""
        return self._raw_config.get(key, default)

    def _find_loader(self, path: Path) -> Optional[ConfigLoader]:
        """查找支持给定路径的加载器。"""
        for loader in self._loaders:
            if loader.supports(path):
                return loader
        return None

    def _apply_profile(
        self, config: dict[str, Any], profile: Optional[str]
    ) -> dict[str, Any]:
        """应用配置配置文件。"""
        if not profile:
            return config

        if profile not in config:
            return config

        # 合并基础配置与配置文件
        base = {k: v for k, v in config.items() if not isinstance(v, dict)}
        profile_config = config.get(profile, {})
        return self._merge_config(base, profile_config)

    def _merge_config(
        self, base: dict[str, Any], override: dict[str, Any]
    ) -> dict[str, Any]:
        """深度合并两个配置。"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        return result


# 便捷函数
def get_config() -> ConfigManager:
    """获取全局配置管理器实例。"""
    return ConfigManager.instance()
