# 服务层

服务层 (`pycore.services`) 提供有状态的长期运行服务，支持状态机管理和步骤式执行。

## 目录

- [概述](#概述)
- [状态机](#状态机)
- [服务基类](#服务基类)
- [服务上下文](#服务上下文)
- [生命周期钩子](#生命周期钩子)
- [高级用法](#高级用法)

---

## 概述

服务层的核心概念：

| 组件 | 描述 |
|------|------|
| `ServiceState` | 服务状态枚举 |
| `StateMachine` | 状态机，管理状态转换 |
| `ServiceContext` | 服务上下文，存储消息和元数据 |
| `BaseService` | 服务基类，提供步骤执行框架 |

### 导入

```python
from pycore.services import ServiceState, StateMachine, BaseService, ServiceContext
# 或
from pycore.services.state import ServiceState, StateMachine
from pycore.services.base import BaseService, ServiceContext
```

---

## 状态机

### 服务状态

```python
class ServiceState(str, Enum):
    IDLE = "idle"           # 空闲，等待启动
    STARTING = "starting"   # 正在启动
    RUNNING = "running"     # 运行中
    PAUSED = "paused"       # 已暂停
    STOPPING = "stopping"   # 正在停止
    STOPPED = "stopped"     # 已停止
    ERROR = "error"         # 错误状态
```

### 状态转换图

```
              ┌─────────────────────────────────┐
              │                                 │
              ▼                                 │
    ┌──────────────┐     ┌──────────────┐      │
    │     IDLE     │────▶│   STARTING   │      │
    └──────────────┘     └──────────────┘      │
           ▲                    │              │
           │                    ▼              │
    ┌──────────────┐     ┌──────────────┐      │
    │   STOPPED    │◀────│   RUNNING    │◀─────┘
    └──────────────┘     └──────────────┘
           ▲                 │     │
           │                 │     │
    ┌──────────────┐         │     ▼
    │   STOPPING   │◀────────┘  ┌──────────────┐
    └──────────────┘            │    PAUSED    │
                                └──────────────┘

    任何状态 ──────────────────▶ ERROR
```

### 创建状态机

```python
from pycore.services import StateMachine, ServiceState

# 使用默认转换规则
sm = StateMachine(use_defaults=True)
print(sm.state)  # ServiceState.IDLE

# 自定义初始状态
sm = StateMachine(initial_state=ServiceState.STOPPED)
```

### 状态转换

```python
# 检查是否可以转换
if sm.can_transition(ServiceState.STARTING):
    sm.transition(ServiceState.STARTING)

# 直接转换（如果不允许会抛出异常）
sm.transition(ServiceState.RUNNING)

# 获取当前状态
print(sm.state)  # ServiceState.RUNNING
print(sm.is_running)  # True
```

### 状态回调

```python
# 进入状态时的回调
def on_enter_running(from_state, to_state):
    print(f"Service started! ({from_state} -> {to_state})")

sm.on_enter(ServiceState.RUNNING, on_enter_running)

# 离开状态时的回调
def on_leave_running(from_state, to_state):
    print(f"Service stopping... ({from_state} -> {to_state})")

sm.on_leave(ServiceState.RUNNING, on_leave_running)

# 触发回调
sm.transition(ServiceState.RUNNING)
# 输出: Service started! (STARTING -> RUNNING)
```

### 自定义转换规则

```python
from pycore.services import StateMachine, ServiceState

# 创建空状态机
sm = StateMachine(use_defaults=False)

# 添加自定义规则
sm.add_transition(ServiceState.IDLE, ServiceState.RUNNING)
sm.add_transition(ServiceState.RUNNING, ServiceState.IDLE)

# 现在只能在 IDLE 和 RUNNING 之间转换
```

---

## 服务基类

### 创建服务

```python
from pycore.services import BaseService

class DataProcessor(BaseService):
    """数据处理服务"""

    name: str = "data_processor"
    max_steps: int = 100

    async def step(self) -> str:
        """
        执行一个处理步骤。

        必须实现此方法。
        返回步骤描述。
        """
        # 获取待处理数据
        items = self.context.get("pending", [])

        if not items:
            return "No items to process"

        # 处理一项
        item = items.pop(0)
        result = await self.process_item(item)

        # 保存结果
        results = self.context.get("results", [])
        results.append(result)
        self.context.set("results", results)

        return f"Processed: {item}"

    async def should_stop(self) -> bool:
        """
        判断是否应该停止。

        可选实现。
        默认返回 False（依赖 max_steps）。
        """
        items = self.context.get("pending", [])
        return len(items) == 0

    async def process_item(self, item):
        """处理单个项目"""
        return item.upper()
```

### 运行服务

```python
import asyncio

async def main():
    # 创建服务
    service = DataProcessor()

    # 设置初始数据
    service.context.set("pending", ["apple", "banana", "cherry"])

    # 运行服务
    result = await service.run()
    print(result)
    # Step 1: Processed: apple
    # Step 2: Processed: banana
    # Step 3: Processed: cherry

    # 获取结果
    results = service.context.get("results")
    print(results)  # ["APPLE", "BANANA", "CHERRY"]

asyncio.run(main())
```

### 带输入运行

```python
# 输入数据会作为 user 消息添加到上下文
result = await service.run("Process this data")

# 在 step 中可以获取
def step(self):
    messages = self.context.get_messages()
    user_input = messages[0].content  # "Process this data"
```

---

## 服务上下文

### ServiceContext 类

服务上下文用于在步骤之间共享数据：

```python
class ServiceContext:
    messages: list[Message]    # 消息历史
    metadata: dict[str, Any]   # 元数据存储
    max_messages: int          # 最大消息数
```

### 消息管理

```python
# 添加消息
service.context.add_message("user", "Hello")
service.context.add_message("assistant", "Hi there!")
service.context.add_message("system", "Remember to be helpful")

# 获取消息
messages = service.context.get_messages()      # 所有消息
recent = service.context.get_messages(n=5)     # 最近 5 条

# 获取为字典列表（用于 LLM 调用）
dicts = service.context.get_messages_as_dicts()
# [{"role": "user", "content": "Hello"}, ...]

# 清空消息
service.context.clear_messages()
```

### 元数据管理

```python
# 设置元数据
service.context.set("user_id", 123)
service.context.set("config", {"timeout": 30})

# 获取元数据
user_id = service.context.get("user_id")
config = service.context.get("config", {})  # 带默认值

# 链式调用
service.context.set("a", 1).set("b", 2).set("c", 3)

# 清空所有
service.context.clear()
```

### 消息限制

```python
# 设置最大消息数
service.context.max_messages = 50

# 超过限制时自动删除旧消息
for i in range(100):
    service.context.add_message("user", f"Message {i}")

len(service.context.messages)  # 50（保留最新的）
```

---

## 生命周期钩子

### 可用钩子

```python
class MyService(BaseService):
    name: str = "my_service"

    async def on_start(self) -> None:
        """
        启动钩子。

        在服务开始运行前调用。
        用于初始化资源。
        """
        self._logger.info("Service starting...")
        # 初始化数据库连接、加载配置等

    async def on_stop(self) -> None:
        """
        停止钩子。

        在服务停止后���用。
        用于清理资源。
        """
        self._logger.info("Service stopping...")
        # 关闭连接、保存状态等

    async def on_error(self, error: Exception) -> None:
        """
        错误钩子。

        在服务发生错误时调用。
        用于错误处理和恢复。
        """
        self._logger.error(f"Service error: {error}")
        # 发送告警、记录日志等

    async def step(self) -> str:
        """步骤执行"""
        return "Step done"
```

### 执行流程

```
1. service.run(input_data)
   │
   ├─▶ 2. state: IDLE -> STARTING
   │       └─▶ on_start()
   │
   ├─▶ 3. state: STARTING -> RUNNING
   │       └─▶ loop:
   │             ├─▶ step()
   │             ├─▶ 检查 stuck 状态
   │             ├─▶ should_stop()
   │             └─▶ 检查 max_steps
   │
   ├─▶ 4. state: RUNNING -> STOPPING
   │       └─▶ on_stop()
   │
   └─▶ 5. state: STOPPING -> STOPPED -> IDLE
```

### 错误处理流程

```
执行过程中发生异常:
   │
   ├─▶ state -> ERROR
   │
   ├─▶ on_error(exception)
   │
   └─▶ 抛出 ServiceError
```

---

## 高级用法

### 暂停和恢复

```python
import asyncio

async def run_with_pause():
    service = MyService()

    # 在后台运行服务
    task = asyncio.create_task(service.run())

    # 等待一段时间后暂停
    await asyncio.sleep(5)
    service.pause()
    print(f"Paused at step {service.current_step}")

    # 做其他事情...
    await asyncio.sleep(2)

    # 恢复执行
    service.resume()
    print("Resumed")

    # 等待完成
    result = await task
```

### 手动停止

```python
async def run_with_stop():
    service = MyService()

    async def stop_after_delay():
        await asyncio.sleep(10)
        service.stop()

    # 启动停止任务
    asyncio.create_task(stop_after_delay())

    # 运行服务
    result = await service.run()
    # 10 秒后会停止
```

### Stuck 检测

服务自动检测重复响应：

```python
class MyService(BaseService):
    name: str = "my_service"
    duplicate_threshold: int = 3  # 重复 3 次视为 stuck

    async def step(self) -> str:
        # 如果连续返回相同内容 3 次，会触发 stuck 处理
        response = await self.get_response()
        self.context.add_message("assistant", response)
        return response
```

当检测到 stuck：
1. 记录警告日志
2. 调用 `_handle_stuck()` 添加系统提示
3. 继续执行

### 状态上下文管理器

```python
async def custom_state_handling(self):
    async with self.state_context(ServiceState.RUNNING):
        # 执行操作
        # 如果抛出异常，自动转换到 ERROR 状态
        await self.do_work()
```

### 继承和扩展

```python
class AIAgent(BaseService):
    """AI Agent 服务"""

    name: str = "ai_agent"
    max_steps: int = 20

    def __init__(self, llm, tools, **data):
        super().__init__(**data)
        self.llm = llm
        self.tools = tools
        self._final_answer = None

    async def step(self) -> str:
        # 构建消息
        messages = self.context.get_messages_as_dicts()

        # 调用 LLM
        response = await self.llm.chat(messages, tools=self.tools)

        if response.has_tool_calls:
            # 执行工具调用
            for tool_call in response.tool_calls:
                result = await self.execute_tool(tool_call)
                self.context.add_message("tool", result, tool_call_id=tool_call.id)
            return f"Executed {len(response.tool_calls)} tools"
        else:
            # 最终答案
            self._final_answer = response.content
            self.context.add_message("assistant", response.content)
            return "Got final answer"

    async def should_stop(self) -> bool:
        return self._final_answer is not None

    async def execute_tool(self, tool_call):
        # 工具执行逻辑
        pass
```

---

## 完整示例

```python
"""服务层完整示例"""

import asyncio
from pycore.core import Logger, LoggerConfig, LogLevel
from pycore.services import BaseService, ServiceState

# 配置日志
logger = Logger.configure(LoggerConfig(level=LogLevel.DEBUG))

class BatchProcessor(BaseService):
    """批量处理服务"""

    name: str = "batch_processor"
    max_steps: int = 1000
    batch_size: int = 10

    async def on_start(self) -> None:
        """初始化"""
        self._processed = 0
        self._errors = 0
        self._logger.info("Batch processor starting")

    async def step(self) -> str:
        """处理一批数据"""
        items = self.context.get("queue", [])

        if not items:
            return "Queue empty"

        # 取一批
        batch = items[:self.batch_size]
        remaining = items[self.batch_size:]
        self.context.set("queue", remaining)

        # 处理
        for item in batch:
            try:
                await self.process_item(item)
                self._processed += 1
            except Exception as e:
                self._errors += 1
                self._logger.warning(f"Failed to process {item}: {e}")

        return f"Processed batch of {len(batch)}, {len(remaining)} remaining"

    async def should_stop(self) -> bool:
        """队列为空时停止"""
        queue = self.context.get("queue", [])
        return len(queue) == 0

    async def on_stop(self) -> None:
        """输出统计"""
        self._logger.info(
            f"Processing complete: {self._processed} succeeded, {self._errors} failed"
        )

    async def on_error(self, error: Exception) -> None:
        """错误处理"""
        self._logger.error(f"Batch processor error: {error}")

    async def process_item(self, item):
        """处理单个项目"""
        await asyncio.sleep(0.01)  # 模拟处理
        return item * 2

async def main():
    # 创建服务
    service = BatchProcessor()

    # 准备数据
    items = list(range(100))
    service.context.set("queue", items)

    logger.info(f"Starting with {len(items)} items")

    # 运行
    result = await service.run()

    # 输出结果
    logger.info(f"Final result:\n{result}")

if __name__ == "__main__":
    asyncio.run(main())
```
