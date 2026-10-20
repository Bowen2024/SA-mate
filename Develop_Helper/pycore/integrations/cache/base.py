"""
缓存提供商的基础类和接口。
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, Union

from pydantic import BaseModel, Field


class CacheConfig(BaseModel):
    """缓存配置。"""

    url: str = Field(
        default="redis://localhost:6379", description="缓存服务器 URL"
    )
    prefix: str = Field(default="pycore:", description="键前缀")
    default_ttl: int = Field(default=3600, description="默认 TTL（秒）")

    class Config:
        extra = "allow"


class CacheProvider(ABC):
    """
    缓存提供商抽象基类。

    用法：
        class RedisProvider(CacheProvider):
            async def get(self, key: str) -> Optional[Any]:
                return await self.client.get(self._make_key(key))

            async def set(self, key: str, value: Any, ttl: int = None) -> bool:
                return await self.client.set(
                    self._make_key(key),
                    value,
                    ex=ttl or self.config.default_ttl
                )

        # 使用
        async with RedisProvider() as cache:
            await cache.set("user:1", {"name": "Alice"})
            user = await cache.get("user:1")
    """

    def __init__(self, config: Optional[CacheConfig] = None, **kwargs):
        if config:
            self.config = config
        else:
            self.config = CacheConfig(**kwargs)

    def _make_key(self, key: str) -> str:
        """生成带前缀的键。"""
        return f"{self.config.prefix}{key}"

    @abstractmethod
    async def connect(self) -> None:
        """建立缓存连接。"""

    @abstractmethod
    async def disconnect(self) -> None:
        """断开缓存连接。"""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值。

        参数：
            key: 缓存键

        返回：
            缓存值，不存在则返回 None
        """

    @abstractmethod
    async def set(
        self, key: str, value: Any, ttl: Optional[int] = None
    ) -> bool:
        """
        设置缓存值。

        参数：
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None 使用默认值

        返回：
            是否设置成功
        """

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        删除缓存。

        参数：
            key: 缓存键

        返回：
            是否删除成功
        """

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        检查键是否存在。

        参数：
            key: 缓存键

        返回：
            键是否存在
        """

    async def get_or_set(
        self,
        key: str,
        factory: Union[Callable, Any],
        ttl: Optional[int] = None,
    ) -> Any:
        """
        获取缓存，不存在则调用工厂函数设置。

        参数：
            key: 缓存键
            factory: 工厂函数或默认值
            ttl: 过期时间（秒）

        返回：
            缓存值
        """
        value = await self.get(key)
        if value is None:
            if callable(factory):
                value = await factory() if hasattr(factory, "__await__") else factory()
            else:
                value = factory
            await self.set(key, value, ttl)
        return value

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
