"""
基础服务类，包含简化的状态机。

提供基本的生命周期管理，适用于需要状态追踪但不需要完整 AI Agent 功能的服务。
"""

from abc import ABC
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from pycore.core.logger import get_logger
from pycore.core.exceptions import ServiceError


class SimpleState(str, Enum):
    """简化的服务状态。"""
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


class BaseService(BaseModel, ABC):
    """
    基础服务类，包含简化的状态机（3 状态）。

    适用于：
    - 需要基本生命周期管理的服务
    - 不需要暂停/恢复功能
    - 不需要卡死检测

    用法：
        class DataProcessor(BaseService):
            name: str = "processor"

            async def process(self, data: Any) -> Any:
                # 处理逻辑
                return processed_data

        service = DataProcessor()
        async with service.running():
            result = await service.process(input_data)
    """

    name: str = Field(..., description="服务名称")
    description: Optional[str] = Field(None, description="服务描述")

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"  # 允许子类添加字段

    def __init__(self, **data):
        super().__init__(**data)
        self._state = SimpleState.IDLE
        self._logger = get_logger().bind(service=self.name)

    @property
    def state(self) -> SimpleState:
        """获取当前服务状态。"""
        return self._state

    @property
    def is_running(self) -> bool:
        """检查服务是否正在运行。"""
        return self._state == SimpleState.RUNNING

    @property
    def is_idle(self) -> bool:
        """检查服务是否空闲。"""
        return self._state == SimpleState.IDLE

    @property
    def is_error(self) -> bool:
        """检查服务是否处于错误状态。"""
        return self._state == SimpleState.ERROR

    @property
    def logger(self):
        """获取绑定的 logger。"""
        return self._logger

    @asynccontextmanager
    async def running(self):
        """
        运行上下文管理器。

        自动管理服务的启动和停止状态。

        用法：
            async with service.running():
                # 服务在这里运行
                await service.do_work()
            # 服务自动回到 IDLE 状态
        """
        if self._state != SimpleState.IDLE:
            raise ServiceError(
                f"Service not idle: {self._state}",
                service_name=self.name,
                state=self._state.value,
            )

        self._state = SimpleState.RUNNING
        self._logger.info("Service started")

        try:
            await self.on_start()
            yield
            await self.on_stop()
        except Exception as e:
            self._state = SimpleState.ERROR
            self._logger.exception(f"Service error: {e}")
            await self.on_error(e)
            raise ServiceError(
                str(e),
                service_name=self.name,
                state=self._state.value,
            )
        finally:
            if self._state != SimpleState.ERROR:
                self._state = SimpleState.IDLE
                self._logger.info("Service stopped")

    async def on_start(self) -> None:
        """服务启动时调用的钩子。重写以实现自定义逻辑。"""
        pass

    async def on_stop(self) -> None:
        """服务停止时调用的钩子。重写以进行清理。"""
        pass

    async def on_error(self, error: Exception) -> None:
        """发生错误时调用的钩子。重写以进行错误处理。"""
        pass

    def reset(self) -> None:
        """重置服务状态为 IDLE。"""
        self._state = SimpleState.IDLE
        self._logger.info("Service reset to IDLE")
