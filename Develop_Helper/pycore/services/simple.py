"""
轻量级服务基类。

不包含状态机，适用于简单的 CRUD 服务。
"""

from abc import ABC
from typing import Any, Optional

from pydantic import BaseModel, Field

from pycore.core.logger import get_logger


class SimpleService(BaseModel, ABC):
    """
    轻量级服务基类。

    适用于：
    - 简单的 CRUD 操作
    - 无状态服务
    - 不需要生命周期管理的场景

    用法：
        class UserService(SimpleService):
            name: str = "user_service"

            async def create_user(self, data: dict) -> dict:
                # 业务逻辑
                return {"id": 1, **data}

            async def get_user(self, user_id: int) -> Optional[dict]:
                # 业务逻辑
                return {"id": user_id, "name": "Alice"}

        # 使用
        service = UserService()
        user = await service.create_user({"name": "Alice"})
    """

    name: str = Field(..., description="服务名称")
    description: Optional[str] = Field(None, description="服务描述")

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"  # 允许子类添加字段

    def __init__(self, **data):
        super().__init__(**data)
        self._logger = get_logger().bind(service=self.name)

    @property
    def logger(self):
        """获取绑定的 logger。"""
        return self._logger

    def log_info(self, message: str, **kwargs) -> None:
        """记录 INFO 级别日志。"""
        self._logger.info(message, **kwargs)

    def log_error(self, message: str, **kwargs) -> None:
        """记录 ERROR 级别日志。"""
        self._logger.error(message, **kwargs)

    def log_debug(self, message: str, **kwargs) -> None:
        """记录 DEBUG 级别日志。"""
        self._logger.debug(message, **kwargs)
