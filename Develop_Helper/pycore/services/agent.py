"""
AI Agent 专用服务类。

包含完整状态机、卡死检测、暂停恢复功能。
"""

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, Optional

from pydantic import BaseModel, Field

from pycore.core.exceptions import ServiceError, ServiceStateError
from pycore.core.logger import get_logger
from pycore.core.schema import Message
from pycore.services.state import ServiceState, StateMachine


class AgentContext(BaseModel):
    """
    AI Agent 的执行上下文。

    存储消息历史、元数据和其他在服务步骤间持久化的上下文信息。

    用法：
        context = AgentContext()
        context.add_message("user", "Hello")
        context.set("key", "value")
        print(context.get("key"))
    """

    messages: list[Message] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    max_messages: int = Field(default=100, description="保留的最大消息数")

    class Config:
        arbitrary_types_allowed = True

    def add_message(
        self,
        role: str,
        content: str,
        **kwargs,
    ) -> "AgentContext":
        """向上下文添加消息。"""
        self.messages.append(Message(role=role, content=content, metadata=kwargs))
        # 如果超过最大值则修剪
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
        return self

    def get_messages(self, n: Optional[int] = None) -> list[Message]:
        """获取最近的消息。"""
        if n is None:
            return self.messages.copy()
        return self.messages[-n:]

    def get_messages_as_dicts(self) -> list[dict[str, Any]]:
        """获取消息字典列表（用于 LLM 调用）。"""
        return [msg.to_dict() for msg in self.messages]

    def set(self, key: str, value: Any) -> "AgentContext":
        """设置元数据值。"""
        self.metadata[key] = value
        return self

    def get(self, key: str, default: Any = None) -> Any:
        """获取元数据值。"""
        return self.metadata.get(key, default)

    def clear_messages(self) -> "AgentContext":
        """清除所有消息。"""
        self.messages.clear()
        return self

    def clear(self) -> "AgentContext":
        """清除所有上下文。"""
        self.messages.clear()
        self.metadata.clear()
        return self


class AgentService(BaseModel, ABC):
    """
    AI Agent 专用服务基类。

    提供：
    - 用于生命周期管理的完整状态机（7 状态）
    - 基于步骤的执行循环
    - 用于状态转换的异步上下文管理器
    - 消息和元数据的上下文管理
    - 卡死检测和处理
    - 暂停/恢复功能

    适用于：
    - AI Agent 对话服务
    - 长期运行的智能服务
    - 需要复杂状态管理的场景

    用法：
        class ChatAgent(AgentService):
            name: str = "chat_agent"

            async def step(self) -> str:
                # 执行一步对话
                response = await llm.chat(self.context.get_messages())
                self.context.add_message("assistant", response)
                return response

            async def should_stop(self) -> bool:
                return "goodbye" in self.context.messages[-1].content.lower()

        # 运行服务
        agent = ChatAgent()
        result = await agent.run("Hello!")
    """

    name: str = Field(..., description="服务名称")
    description: Optional[str] = Field(None, description="服务描述")

    context: AgentContext = Field(default_factory=AgentContext)
    max_steps: int = Field(default=100, description="最大执行步数")
    current_step: int = Field(default=0, description="当前步数")

    # 卡死检测
    duplicate_threshold: int = Field(
        default=3, description="在认为卡死之前的重复次数"
    )

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"  # 允许子类扩展

    def __init__(self, **data):
        super().__init__(**data)
        self._state_machine = StateMachine(use_defaults=True)
        self._logger = get_logger().bind(service=self.name)

    @property
    def state(self) -> ServiceState:
        """获取当前服务状态。"""
        return self._state_machine.state

    @property
    def is_running(self) -> bool:
        """检查服务是否正在运行。"""
        return self._state_machine.is_running

    @asynccontextmanager
    async def state_context(self, new_state: ServiceState):
        """
        用于安全状态转换的上下文管理器。

        通过转换到 ERROR 状态自动处理错误。

        用法：
            async with self.state_context(ServiceState.RUNNING):
                await self.do_work()
        """
        try:
            self._state_machine.transition(new_state)
            yield
        except Exception as e:
            if self._state_machine.can_transition(ServiceState.ERROR):
                self._state_machine.transition(ServiceState.ERROR)
            raise

    async def run(self, input_data: Optional[str] = None) -> str:
        """
        执行服务主循环。

        参数：
            input_data: 可选的初始输入

        返回：
            所有步骤的合并结果

        抛出：
            ServiceError: 如果服务无法启动
        """
        if self.state != ServiceState.IDLE:
            raise ServiceStateError(
                f"Cannot start service from state: {self.state}",
                service_name=self.name,
                from_state=self.state.value,
                to_state=ServiceState.STARTING.value,
            )

        # 将输入添加到上下文
        if input_data:
            self.context.add_message("user", input_data)

        results: list[str] = []

        try:
            # 启动阶段
            async with self.state_context(ServiceState.STARTING):
                self._logger.info("Service starting")
                await self.on_start()

            # 运行阶段
            async with self.state_context(ServiceState.RUNNING):
                self._logger.info("Service running")

                while self.current_step < self.max_steps:
                    if self.state != ServiceState.RUNNING:
                        break

                    self.current_step += 1
                    self._logger.debug(
                        f"Executing step {self.current_step}/{self.max_steps}"
                    )

                    # 执行步骤
                    step_result = await self.step()
                    results.append(f"Step {self.current_step}: {step_result}")

                    # 检查卡死状态
                    if self._is_stuck():
                        self._logger.warning("Stuck state detected")
                        self._handle_stuck()

                    # 检查是否应该停止
                    if await self.should_stop():
                        self._logger.info("Stop condition met")
                        break

                if self.current_step >= self.max_steps:
                    self._logger.warning(f"Reached max steps: {self.max_steps}")
                    results.append(f"Reached max steps ({self.max_steps})")

            # 停止阶段
            async with self.state_context(ServiceState.STOPPING):
                self._logger.info("Service stopping")
                await self.on_stop()

            # 重置为空闲
            self._state_machine.transition(ServiceState.STOPPED)
            self._state_machine.transition(ServiceState.IDLE)

        except Exception as e:
            self._logger.exception(f"Service error: {e}")
            await self.on_error(e)
            raise ServiceError(str(e), service_name=self.name, state=self.state.value)

        finally:
            # 重置步数计数器
            self.current_step = 0

        return "\n".join(results) if results else "No steps executed"

    @abstractmethod
    async def step(self) -> str:
        """
        执行单个步骤。

        必须由子类实现。

        返回：
            步骤结果描述
        """

    async def should_stop(self) -> bool:
        """
        检查执行是否应该停止。

        重写以实现自定义停止条件。
        默认：永不停止（依赖 max_steps）。
        """
        return False

    async def on_start(self) -> None:
        """服务启动时调用的钩子。重写以实现自定义逻辑。"""
        pass

    async def on_stop(self) -> None:
        """服务停止时调用的钩子。重写以进行清理。"""
        pass

    async def on_error(self, error: Exception) -> None:
        """发生错误时调用的钩子。重写以进行错误处理。"""
        pass

    def _is_stuck(self) -> bool:
        """检测服务是否处于卡死循环。"""
        messages = self.context.messages
        if len(messages) < 2:
            return False

        last_content = messages[-1].content
        if not last_content:
            return False

        # 计算连续相同的消息数
        count = 0
        for msg in reversed(messages[:-1]):
            if msg.role == "assistant" and msg.content == last_content:
                count += 1
            else:
                break

        return count >= self.duplicate_threshold

    def _handle_stuck(self) -> None:
        """通过添加上下文处理卡死状态。"""
        self.context.add_message(
            "system",
            "Detected repetitive responses. Consider alternative approaches.",
        )

    def pause(self) -> None:
        """暂停服务执行。"""
        if self._state_machine.can_transition(ServiceState.PAUSED):
            self._state_machine.transition(ServiceState.PAUSED)
            self._logger.info("Service paused")

    def resume(self) -> None:
        """恢复服务执行。"""
        if self.state == ServiceState.PAUSED:
            self._state_machine.transition(ServiceState.RUNNING)
            self._logger.info("Service resumed")

    def stop(self) -> None:
        """请求停止服务。"""
        if self._state_machine.can_transition(ServiceState.STOPPING):
            self._state_machine.transition(ServiceState.STOPPING)
            self._logger.info("Service stop requested")


# 向后兼容别名
ServiceContext = AgentContext
