"""
Cache integration module.

提供缓存操作的统一抽象。
"""

from pycore.integrations.cache.base import (
    CacheProvider,
    CacheConfig,
)

__all__ = [
    "CacheProvider",
    "CacheConfig",
]
