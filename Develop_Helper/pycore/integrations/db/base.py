"""
数据库提供商的基础类和接口。
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field


class DatabaseConfig(BaseModel):
    """数据库配置。"""

    url: str = Field(..., description="数据库连接 URL")
    pool_size: int = Field(default=5, description="连接池大小")
    max_overflow: int = Field(default=10, description="最大溢出连接数")
    echo: bool = Field(default=False, description="是否打印 SQL")

    class Config:
        extra = "allow"


class DatabaseProvider(ABC):
    """
    数据库提供商抽象基类。

    用法：
        class SQLAlchemyProvider(DatabaseProvider):
            async def execute(self, query, params=None):
                async with self.session() as session:
                    result = await session.execute(query, params)
                    return result.fetchall()

        # 使用
        async with SQLAlchemyProvider(url="postgresql://...") as db:
            users = await db.fetch_all("SELECT * FROM users")
    """

    def __init__(self, config: Optional[DatabaseConfig] = None, **kwargs):
        if config:
            self.config = config
        else:
            self.config = DatabaseConfig(**kwargs)

    @abstractmethod
    async def connect(self) -> None:
        """建立数据库连接。"""

    @abstractmethod
    async def disconnect(self) -> None:
        """断开数据库连接。"""

    @abstractmethod
    async def execute(self, query: str, params: Optional[dict] = None) -> Any:
        """
        执行查询。

        参数：
            query: SQL 查询语句
            params: 查询参数

        返回：
            执行结果
        """

    @abstractmethod
    async def fetch_one(
        self, query: str, params: Optional[dict] = None
    ) -> Optional[dict]:
        """
        获取单条记录。

        参数：
            query: SQL 查询语句
            params: 查询参数

        返回：
            单条记录字典，不存在则返回 None
        """

    @abstractmethod
    async def fetch_all(
        self, query: str, params: Optional[dict] = None
    ) -> list[dict]:
        """
        获取所有记录。

        参数：
            query: SQL 查询语句
            params: 查询参数

        返回：
            记录字典列表
        """

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
