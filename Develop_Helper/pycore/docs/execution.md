# 执行层

执行层 (`pycore.execution`) 提供执行上下文管理和流程编排功能。

## 目录

- [概述](#概述)
- [执行上下文](#执行上下文)
- [流程编排](#流程编排)
- [顺序流程](#顺序流程)
- [并行流程](#并行流程)
- [自定义流程](#自定义流程)

---

## 概述

执行层的核心概念：

| 组件 | 描述 |
|------|------|
| `ExecutionContext` | 使用 contextvars 的请求级上下文 |
| `FlowStep` | 流程步骤定义 |
| `FlowResult` | 流程执行结果 |
| `BaseFlow` | 流程基类 |
| `SequentialFlow` | 顺序执行流程 |
| `ParallelFlow` | 并行执行流程 |

### 导入

```python
from pycore.execution import (
    ExecutionContext,
    execution_context,
    BaseFlow,
    FlowStep,
    FlowResult,
    SequentialFlow,
    ParallelFlow,
)
```

---

## 执行上下文

执行上下文使用 Python 的 `contextvars` 实现，提供线程安全和异步安全的请求级数据共享。

### 基本用法

```python
from pycore.execution import ExecutionContext

# 创建上下文作用域
async with ExecutionContext.scope(request_id="abc123", user_id=456):
    # 在作用域内的任意位置访问
    request_id = ExecutionContext.get("request_id")  # "abc123"
    user_id = ExecutionContext.get("user_id")        # 456

    # 修改上下文
    ExecutionContext.set("processed", True)

    # 调用其他函数，上下文自动传递
    await process_request()

# 作用域外，上下文恢复
ExecutionContext.get("request_id")  # None
```

### 同步版本

```python
# 同步上下文作用域
with ExecutionContext.sync_scope(key="value"):
    data = ExecutionContext.get("key")  # "value"
```

### 嵌套作用域

```python
async with ExecutionContext.scope(a=1, b=2):
    print(ExecutionContext.get("a"))  # 1
    print(ExecutionContext.get("b"))  # 2

    # 嵌套作用域继承父级
    async with ExecutionContext.nested_scope(c=3):
        print(ExecutionContext.get("a"))  # 1 (继承)
        print(ExecutionContext.get("b"))  # 2 (继承)
        print(ExecutionContext.get("c"))  # 3 (新增)

    # 退出嵌套后，c 不可用
    print(ExecutionContext.get("c"))  # None
```

### 上下文操作

```python
# 设置值
ExecutionContext.set("key", "value")

# 获取值
value = ExecutionContext.get("key")
value = ExecutionContext.get("key", "default")  # 带默认值

# 更新多个值
ExecutionContext.update(a=1, b=2, c=3)

# 检查是否存在
if ExecutionContext.has("key"):
    ...

# 删除值
ExecutionContext.delete("key")

# 清空所有
ExecutionContext.clear()

# 获取当前上下文副本
ctx = ExecutionContext.current()  # dict
```

### 快捷函数

```python
from pycore.execution import execution_context

# 获取当前上下文字典
ctx = execution_context()
print(ctx)  # {"request_id": "abc123", "user_id": 456, ...}
```

### 实际应用示例

```python
from pycore.execution import ExecutionContext

async def api_handler(request):
    """API 请求处理器"""
    async with ExecutionContext.scope(
        request_id=request.headers.get("X-Request-ID"),
        user_id=request.user.id,
        path=request.url.path,
        method=request.method,
    ):
        return await process_request(request)

async def process_request(request):
    """处理请求"""
    # 无需显式传递参数，直接从上下文获取
    logger = get_logger().bind(
        request_id=ExecutionContext.get("request_id"),
        user_id=ExecutionContext.get("user_id"),
    )

    logger.info("Processing request")

    # 调用更深层的函数
    result = await business_logic()

    return result

async def business_logic():
    """业务逻辑"""
    # 依然可以访问上下文
    user_id = ExecutionContext.get("user_id")
    # ...
```

---

## 流程编排

流程编排提供多步骤工作流的组织和执行。

### FlowStep - 流程步骤

```python
from pycore.execution import FlowStep

# 定义步骤
step = FlowStep(
    name="process_data",
    handler=process_function,      # 处理函数
    config={"timeout": 30},        # 配置参数
    depends_on=["fetch_data"],     # 依赖步骤
    retry_count=3,                 # 重���次数
    timeout=60.0,                  # 超时时间（秒）
)
```

### FlowResult - 流程结果

```python
from pycore.execution import FlowResult

# 成功结果
result = FlowResult.ok(
    output="Final output",
    step_results={"step1": data1, "step2": data2}
)

# 失败结果
result = FlowResult.fail(
    error="Step 'process' failed: timeout",
    step_results={"step1": data1}  # 已完成的步骤结果
)

# 使用结果
if result.success:
    print(result.output)
    print(result.step_results)
else:
    print(result.error)

# 布尔判断
if result:
    process(result.output)
```

---

## 顺序流程

顺序流程按顺序执行步骤，每个步骤接收上一步的输出。

### 基本用法

```python
from pycore.execution import SequentialFlow

# 定义处理函数
async def fetch_data(input_data, **config):
    """获取数据"""
    return {"raw": input_data}

async def transform(data, **config):
    """转换数据"""
    return {"transformed": data["raw"].upper()}

async def save(data, **config):
    """保存数据"""
    return f"Saved: {data['transformed']}"

# 创建流程
flow = SequentialFlow(name="data_pipeline")

# 添加步骤
flow.add_step("fetch", fetch_data)
flow.add_step("transform", transform)
flow.add_step("save", save)

# 执行
result = await flow.run("hello world")

print(result.success)      # True
print(result.output)       # "Saved: HELLO WORLD"
print(result.step_results) # {"fetch": {...}, "transform": {...}, "save": "..."}
```

### 带配置的步骤

```python
flow = SequentialFlow(name="pipeline")

# 步骤配置会传递给处理函数
flow.add_step("fetch", fetch_data, source="api", retries=3)
flow.add_step("transform", transform, format="json")

# 处理函数签名
async def fetch_data(input_data, source=None, retries=1, **kwargs):
    # source="api", retries=3
    ...
```

### 超时设置

```python
from pycore.execution import FlowStep

# 方式1：通过 add_step
flow.add_step("slow_step", slow_function, timeout=30.0)

# 方式2：手动创建 FlowStep
step = FlowStep(
    name="slow_step",
    handler=slow_function,
    timeout=30.0,
)
flow.steps.append(step)
```

### 错误处理

```python
result = await flow.run(input_data)

if not result.success:
    print(f"Error: {result.error}")
    # Error: Step 'transform' failed: ValueError: invalid data

    # 查看已完成的步骤
    print(result.step_results)
    # {"fetch": {...}}  # transform 失败前的结果
```

---

## 并行流程

并行流程同时执行所有步骤，所有步骤接收相同的输入。

### 基本用法

```python
from pycore.execution import ParallelFlow

# 定义独立任务
async def check_api(input_data, **config):
    return {"api": "ok"}

async def check_db(input_data, **config):
    return {"db": "ok"}

async def check_cache(input_data, **config):
    return {"cache": "ok"}

# 创建并行流程
flow = ParallelFlow(name="health_check")

flow.add_step("api", check_api)
flow.add_step("db", check_db)
flow.add_step("cache", check_cache)

# 执行（所有任务并行运行）
result = await flow.run("check")

print(result.step_results)
# {
#     "api": {"api": "ok"},
#     "db": {"db": "ok"},
#     "cache": {"cache": "ok"}
# }
```

### 并发限制

```python
# 限制同时运行的任务数
flow = ParallelFlow(
    name="limited_parallel",
    max_concurrency=3,  # 最多 3 个并发
)

# 添加 10 个任务
for i in range(10):
    flow.add_step(f"task_{i}", process_task)

# 执行时最多 3 个任务同时运行
result = await flow.run(data)
```

### 部分失败处理

```python
# 并行流程中，某些任务失败不会阻止其他任务
result = await flow.run(data)

if not result.success:
    print(f"Errors: {result.error}")
    # Parallel execution errors: task_2: timeout; task_5: connection error

    # 成功的任务结果仍然可用
    print(result.step_results)
    # {"task_0": ..., "task_1": ..., "task_3": ..., ...}
```

---

## 自定义流程

### 继承 BaseFlow

```python
from pycore.execution import BaseFlow, FlowResult

class ConditionalFlow(BaseFlow):
    """条件分支流程"""

    name: str = "conditional"
    condition_key: str = "type"

    async def execute(self, input_data: dict) -> FlowResult:
        """根据条件执行不同分支"""
        condition = input_data.get(self.condition_key)

        if condition == "A":
            result = await self.process_type_a(input_data)
        elif condition == "B":
            result = await self.process_type_b(input_data)
        else:
            return FlowResult.fail(f"Unknown type: {condition}")

        return FlowResult.ok(result)

    async def process_type_a(self, data):
        return {"processed": "A", "data": data}

    async def process_type_b(self, data):
        return {"processed": "B", "data": data}

# 使用
flow = ConditionalFlow()
result = await flow.run({"type": "A", "value": 123})
```

### 生命周期钩子

```python
class MyFlow(BaseFlow):
    name: str = "my_flow"

    async def before_execute(self, input_data) -> None:
        """执行前钩子"""
        self._logger.info(f"Starting flow with: {input_data}")
        # 验证输入、初始化资源等

    async def execute(self, input_data) -> FlowResult:
        """主执行逻辑"""
        # ...
        return FlowResult.ok(result)

    async def after_execute(self, result: FlowResult) -> FlowResult:
        """执行后钩子"""
        self._logger.info(f"Flow completed: {result.success}")
        # 可以修改结果
        result.metadata["completed_at"] = datetime.now().isoformat()
        return result
```

### 复合流程

```python
class PipelineFlow(BaseFlow):
    """组合顺序和并行流程"""

    name: str = "pipeline"

    def __init__(self, **data):
        super().__init__(**data)
        self._setup_flows()

    def _setup_flows(self):
        # 第一阶段：获取数据
        self.fetch_flow = SequentialFlow(name="fetch")
        self.fetch_flow.add_step("validate", validate_input)
        self.fetch_flow.add_step("fetch", fetch_data)

        # 第二阶段：并行处理
        self.process_flow = ParallelFlow(name="process")
        self.process_flow.add_step("analyze", analyze_data)
        self.process_flow.add_step("transform", transform_data)
        self.process_flow.add_step("enrich", enrich_data)

        # 第三阶段：合并保存
        self.save_flow = SequentialFlow(name="save")
        self.save_flow.add_step("merge", merge_results)
        self.save_flow.add_step("save", save_data)

    async def execute(self, input_data) -> FlowResult:
        # 阶段1
        result = await self.fetch_flow.run(input_data)
        if not result:
            return result

        # 阶段2
        result = await self.process_flow.run(result.output)
        if not result:
            return result

        # 阶段3
        result = await self.save_flow.run(result.step_results)
        return result
```

---

## 完整示例

```python
"""执行层完整示例"""

import asyncio
from pycore.core import Logger, LoggerConfig, LogLevel
from pycore.execution import (
    ExecutionContext,
    SequentialFlow,
    ParallelFlow,
    FlowResult,
)

# 配置日志
logger = Logger.configure(LoggerConfig(level=LogLevel.DEBUG))

# 处理函数
async def fetch_user(user_id, **config):
    """获取用户信息"""
    logger.debug(f"Fetching user {user_id}")
    await asyncio.sleep(0.1)  # 模拟 API 调用
    return {"id": user_id, "name": f"User_{user_id}"}

async def fetch_orders(user_data, **config):
    """获取用户订单"""
    logger.debug(f"Fetching orders for {user_data['id']}")
    await asyncio.sleep(0.1)
    return {
        "user": user_data,
        "orders": [{"id": 1, "amount": 100}, {"id": 2, "amount": 200}]
    }

async def calculate_total(data, **config):
    """计算总额"""
    total = sum(order["amount"] for order in data["orders"])
    return {**data, "total": total}

# 并行任务
async def send_email(data, **config):
    """发送邮件"""
    logger.debug(f"Sending email to {data['user']['name']}")
    await asyncio.sleep(0.1)
    return {"email": "sent"}

async def update_stats(data, **config):
    """更新统计"""
    logger.debug("Updating stats")
    await asyncio.sleep(0.05)
    return {"stats": "updated"}

async def main():
    # 创建顺序流程
    data_flow = SequentialFlow(name="user_data")
    data_flow.add_step("fetch_user", fetch_user)
    data_flow.add_step("fetch_orders", fetch_orders)
    data_flow.add_step("calculate", calculate_total)

    # 创建并行流程
    notify_flow = ParallelFlow(name="notifications")
    notify_flow.add_step("email", send_email)
    notify_flow.add_step("stats", update_stats)

    # 使用执行上下文
    async with ExecutionContext.scope(request_id="req_123"):
        logger.info("Starting data processing")

        # 运行顺序流程
        result = await data_flow.run(user_id=42)

        if result.success:
            logger.info(f"Data flow completed: total={result.output['total']}")

            # 运行并行流程
            notify_result = await notify_flow.run(result.output)

            if notify_result.success:
                logger.info("All notifications sent")
            else:
                logger.warning(f"Notification errors: {notify_result.error}")
        else:
            logger.error(f"Data flow failed: {result.error}")

        # 查看请求 ID
        logger.info(f"Request completed: {ExecutionContext.get('request_id')}")

if __name__ == "__main__":
    asyncio.run(main())
```

输出示例：
```
2024-01-01 12:00:00 | INFO  | Starting data processing
2024-01-01 12:00:00 | DEBUG | Fetching user 42
2024-01-01 12:00:00 | DEBUG | Fetching orders for 42
2024-01-01 12:00:00 | INFO  | Data flow completed: total=300
2024-01-01 12:00:00 | DEBUG | Sending email to User_42
2024-01-01 12:00:00 | DEBUG | Updating stats
2024-01-01 12:00:00 | INFO  | All notifications sent
2024-01-01 12:00:00 | INFO  | Request completed: req_123
```
