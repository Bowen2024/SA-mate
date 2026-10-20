"""
基于流程的工作流执行。

提供组合和执行多步骤工作流的模式。
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from pycore.core.exceptions import ExecutionError
from pycore.core.logger import get_logger


class FlowStep(BaseModel):
    """
    表示流程中的一个步骤。

    用法：
        step = FlowStep(
            name="process_data",
            handler=process_function,
            config={"timeout": 30}
        )
    """

    name: str = Field(..., description="步骤名称")
    handler: Callable = Field(..., description="步骤处理器")
    config: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(
        default_factory=list, description="此步骤依赖的步骤"
    )
    retry_count: int = Field(default=0, description="失败时的重试次数")
    timeout: Optional[float] = Field(None, description="步骤超时时间（秒）")

    class Config:
        arbitrary_types_allowed = True


class FlowResult(BaseModel):
    """
    流程执行结果。

    用法：
        if result:
            print(result.data)
        else:
            print(result.error)
    """

    success: bool = True
    data: Any = None
    error: Optional[str] = None
    step_results: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True

    def __bool__(self) -> bool:
        return self.success

    @property
    def output(self) -> Any:
        """向后兼容：output -> data"""
        return self.data

    @classmethod
    def ok(cls, data: Any, step_results: Optional[dict] = None, **metadata) -> "FlowResult":
        """创建成功结果。"""
        return cls(
            success=True,
            data=data,
            step_results=step_results or {},
            metadata=metadata,
        )

    @classmethod
    def fail(cls, error: str, step_results: Optional[dict] = None, **metadata) -> "FlowResult":
        """创建失败结果。"""
        return cls(
            success=False,
            error=error,
            step_results=step_results or {},
            metadata=metadata,
        )


class BaseFlow(BaseModel, ABC):
    """
    执行流程的抽象基础类。

    流程编排多步骤过程，包括：
    - 逐步执行
    - 错误处理
    - 前后钩子

    用法：
        class MyFlow(BaseFlow):
            async def execute(self, input_data: str) -> FlowResult:
                # 流程逻辑
                return FlowResult.ok("Done")

        flow = MyFlow(name="my_flow")
        result = await flow.run("input")
    """

    name: str = Field(..., description="Flow name")
    description: Optional[str] = Field(None)
    steps: list[FlowStep] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data):
        super().__init__(**data)
        self._logger = get_logger().bind(flow=self.name)

    async def run(self, input_data: Any) -> FlowResult:
        """
        使用输入数据运行流程。

        用前后钩子和错误处理包装 execute()。
        """
        self._logger.info(f"Starting flow: {self.name}")

        try:
            await self.before_execute(input_data)
            result = await self.execute(input_data)
            result = await self.after_execute(result)
            self._logger.info(f"Flow completed: {self.name}", success=result.success)
            return result

        except Exception as e:
            self._logger.exception(f"Flow failed: {self.name}")
            return FlowResult.fail(str(e))

    @abstractmethod
    async def execute(self, input_data: Any) -> FlowResult:
        """执行流程。必须由子类实现。"""

    async def before_execute(self, input_data: Any) -> None:
        """执行前调用的钩子。重写以进行设置。"""
        pass

    async def after_execute(self, result: FlowResult) -> FlowResult:
        """执行后调用的钩子。重写以进行清理/转换。"""
        return result

    def add_step(
        self,
        name: str,
        handler: Callable,
        **config,
    ) -> "BaseFlow":
        """向流程添加步骤。"""
        step = FlowStep(name=name, handler=handler, config=config)
        self.steps.append(step)
        return self


class SequentialFlow(BaseFlow):
    """
    按顺序执行步骤。

    每个步骤接收前一个步骤的输出。

    用法：
        flow = SequentialFlow(name="pipeline")
        flow.add_step("step1", process_step1)
        flow.add_step("step2", process_step2)
        result = await flow.run("input")
    """

    name: str = "sequential"

    async def execute(self, input_data: Any) -> FlowResult:
        step_results: dict[str, Any] = {}
        current_data = input_data

        for step in self.steps:
            self._logger.debug(f"Executing step: {step.name}")

            try:
                # 获取处理器
                handler = step.handler

                # 使用可选超时执行
                if step.timeout:
                    current_data = await asyncio.wait_for(
                        self._execute_handler(handler, current_data, step.config),
                        timeout=step.timeout,
                    )
                else:
                    current_data = await self._execute_handler(
                        handler, current_data, step.config
                    )

                step_results[step.name] = current_data
                self._logger.debug(f"Step completed: {step.name}")

            except asyncio.TimeoutError:
                return FlowResult.fail(
                    f"Step '{step.name}' timed out after {step.timeout}s",
                    step_results=step_results,
                )
            except Exception as e:
                return FlowResult.fail(
                    f"Step '{step.name}' failed: {e}",
                    step_results=step_results,
                )

        return FlowResult.ok(current_data, step_results=step_results)

    async def _execute_handler(
        self,
        handler: Callable,
        data: Any,
        config: dict,
    ) -> Any:
        """Execute a step handler."""
        if asyncio.iscoroutinefunction(handler):
            return await handler(data, **config)
        else:
            return handler(data, **config)


class ParallelFlow(BaseFlow):
    """
    并行执行步骤。

    所有步骤接收相同的输入并并发运行。

    用法：
        flow = ParallelFlow(name="parallel_tasks")
        flow.add_step("task1", process_task1)
        flow.add_step("task2", process_task2)
        result = await flow.run("input")
        # result.step_results 包含每个步骤的输出
    """

    name: str = "parallel"
    max_concurrency: Optional[int] = Field(
        None, description="Maximum concurrent tasks"
    )

    async def execute(self, input_data: Any) -> FlowResult:
        if not self.steps:
            return FlowResult.ok(None, step_results={})

        step_results: dict[str, Any] = {}
        errors: list[str] = []

        # 创建任务
        tasks = []
        for step in self.steps:
            task = self._execute_step(step, input_data)
            tasks.append((step.name, task))

        # 使用可选并发限制执行
        if self.max_concurrency:
            semaphore = asyncio.Semaphore(self.max_concurrency)

            async def limited_task(name: str, coro):
                async with semaphore:
                    return name, await coro

            results = await asyncio.gather(
                *[limited_task(name, task) for name, task in tasks],
                return_exceptions=True,
            )
        else:
            results = await asyncio.gather(
                *[self._wrap_task(name, task) for name, task in tasks],
                return_exceptions=True,
            )

        # 处理结果
        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
            else:
                name, output = result
                step_results[name] = output

        if errors:
            return FlowResult.fail(
                f"Parallel execution errors: {'; '.join(errors)}",
                step_results=step_results,
            )

        return FlowResult.ok(step_results, step_results=step_results)

    async def _wrap_task(self, name: str, coro) -> tuple[str, Any]:
        """用名称包装任务以便结果映射。"""
        result = await coro
        return name, result

    async def _execute_step(self, step: FlowStep, input_data: Any) -> Any:
        """执行单个步骤。"""
        handler = step.handler
        config = step.config

        try:
            if step.timeout:
                return await asyncio.wait_for(
                    self._execute_handler(handler, input_data, config),
                    timeout=step.timeout,
                )
            else:
                return await self._execute_handler(handler, input_data, config)
        except asyncio.TimeoutError:
            raise ExecutionError(
                f"Step '{step.name}' timed out",
                flow_name=self.name,
                step=step.name,
            )

    async def _execute_handler(
        self,
        handler: Callable,
        data: Any,
        config: dict,
    ) -> Any:
        """Execute a step handler."""
        if asyncio.iscoroutinefunction(handler):
            return await handler(data, **config)
        else:
            return handler(data, **config)
