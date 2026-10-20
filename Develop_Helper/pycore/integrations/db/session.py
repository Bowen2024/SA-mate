"""
数据库会话管理模板。

新项目基于此模板配置异步数据库引擎和会话。
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pycore.core.config import get_config
from pycore.core.logger import get_logger

logger = get_logger()

# 从配置读取数据库 URL（新项目需在配置中定义 database_url）
_config = get_config()
DATABASE_URL: str = getattr(_config.settings, "database_url", "sqlite+aiosqlite:///./app.db")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（用于 FastAPI Depends）。"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """上下文管理器形式的数据库会话。"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """初始化数据库（创建表）。新项目应在 main.py lifespan 中调用。"""
    from pycore.integrations.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")


async def close_db() -> None:
    """关闭数据库连接。新项目应在 main.py lifespan 中调用。"""
    await engine.dispose()
    logger.info("Database connection closed")
