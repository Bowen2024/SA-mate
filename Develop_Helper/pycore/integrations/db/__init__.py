"""
Database integration module.

提供数据库操作的统一抽象。
"""

from pycore.integrations.db.base import (
    DatabaseProvider,
    DatabaseConfig,
)

__all__ = [
    "DatabaseProvider",
    "DatabaseConfig",
]
