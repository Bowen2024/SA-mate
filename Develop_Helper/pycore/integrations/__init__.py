"""
Integrations module for PyCore.

提供外部服务集成：
- llm: LLM 提供商（OpenAI 等）
- db: 数据库抽象
- cache: 缓存抽象
"""

from pycore.integrations.llm import (
    LLMProvider,
    LLMConfig,
    LLMResponse,
    Message,
    OpenAIProvider,
    create_provider,
)
from pycore.integrations.db import DatabaseProvider, DatabaseConfig
from pycore.integrations.cache import CacheProvider, CacheConfig

__all__ = [
    # LLM
    "LLMProvider",
    "LLMConfig",
    "LLMResponse",
    "Message",
    "OpenAIProvider",
    "create_provider",
    # Database
    "DatabaseProvider",
    "DatabaseConfig",
    # Cache
    "CacheProvider",
    "CacheConfig",
]
