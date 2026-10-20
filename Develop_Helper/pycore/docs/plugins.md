# 插件系统

插件系统 (`pycore.plugins`) 提供可扩展的功能单元，用于封装可复用的业务逻辑。

## 目录

- [概述](#概述)
- [创建插件](#创建插件)
- [插件注册表](#插件注册表)
- [插件结果](#插件结果)
- [生命周期](#生命周期)
- [高级用法](#高级用法)

---

## 概述

插件系统的核心概念：

| 组件 | 描述 |
|------|------|
| `BasePlugin` | 插件基类，定义插件接口 |
| `PluginResult` | 插件执行结果 |
| `PluginRegistry` | 插件注册表，管理插件集合 |

### 导入

```python
from pycore.plugins import BasePlugin, PluginResult, PluginRegistry
# 或
from pycore.plugins.base import BasePlugin, PluginResult
from pycore.plugins.registry import PluginRegistry
```

---

## 创建插件

### 基本插件

```python
from pycore.plugins import BasePlugin, PluginResult

class GreetPlugin(BasePlugin):
    """问候插件"""

    # 必需字段
    name: str = "greet"
    description: str = "Say hello to someone"

    # 可选字段
    version: str = "1.0.0"

    async def execute(self, name: str, **kwargs) -> PluginResult:
        """
        执行插件逻辑。

        Args:
            name: 要问候的名字
            **kwargs: 额外参数

        Returns:
            PluginResult: 执行结果
        """
        greeting = f"Hello, {name}!"
        return self.success(greeting)
```

### 带参数验证的插件

```python
from typing import Optional
from pycore.plugins import BasePlugin, PluginResult

class CalculatorPlugin(BasePlugin):
    """计算器插件"""

    name: str = "calculator"
    description: str = "Perform basic calculations"

    async def execute(
        self,
        a: float,
        b: float,
        operation: str = "add",
        **kwargs,
    ) -> PluginResult:
        """执行计算"""
        operations = {
            "add": lambda: a + b,
            "sub": lambda: a - b,
            "mul": lambda: a * b,
            "div": lambda: a / b if b != 0 else None,
        }

        if operation not in operations:
            return self.failure(f"Unknown operation: {operation}")

        result = operations[operation]()

        if result is None:
            return self.failure("Division by zero")

        return self.success(result)
```

### 带状态的插件

```python
from pycore.plugins import BasePlugin, PluginResult

class CounterPlugin(BasePlugin):
    """计数器插件"""

    name: str = "counter"
    description: str = "Count invocations"

    # 插件状态
    _count: int = 0

    async def execute(self, increment: int = 1, **kwargs) -> PluginResult:
        """增加计数"""
        self._count += increment
        return self.success(
            self._count,
            metadata={"total_calls": self._count}
        )

    async def setup(self) -> None:
        """初始化计数器"""
        self._count = 0
        self._logger.info("Counter initialized")

    async def teardown(self) -> None:
        """清理"""
        self._logger.info(f"Counter final value: {self._count}")
```

### 带外部依赖的插件

```python
from pycore.plugins import BasePlugin, PluginResult

class DatabasePlugin(BasePlugin):
    """数据库查询插件"""

    name: str = "database"
    description: str = "Query database"

    _connection = None

    async def setup(self) -> None:
        """建立数据库连接"""
        # self._connection = await create_connection(...)
        self._logger.info("Database connected")

    async def teardown(self) -> None:
        """关闭连接"""
        if self._connection:
            # await self._connection.close()
            pass
        self._logger.info("Database disconnected")

    async def execute(self, query: str, **kwargs) -> PluginResult:
        """执行查询"""
        if not self._connection:
            return self.failure("Database not connected")

        try:
            # result = await self._connection.execute(query)
            result = {"rows": []}  # 模拟
            return self.success(result)
        except Exception as e:
            return self.failure(f"Query failed: {e}")
```

---

## 插件注册表

### 创建和注册

```python
from pycore.plugins import PluginRegistry

# 创建注册表
registry = PluginRegistry()

# 注册插件实例
registry.register(GreetPlugin())
registry.register(CalculatorPlugin())
registry.register(CounterPlugin())

# 注册时自动调用 setup()
```

### 执行插件

```python
# 按名称执行
result = await registry.execute("greet", name="World")
print(result.output)  # "Hello, World!"

# 带关键字参数
result = await registry.execute("calculator", a=10, b=5, operation="mul")
print(result.output)  # 50

# 不存在的插件
result = await registry.execute("unknown", data="test")
print(result.success)  # False
print(result.output)   # "Plugin not found: unknown"
```

### 检查和获取

```python
# 检查插件是否存在
if registry.has("calculator"):
    result = await registry.execute("calculator", a=1, b=2)

# 获取插件实例
plugin = registry.get("greet")
if plugin:
    print(f"Found: {plugin.name} v{plugin.version}")

# 获取所有插件名称
names = registry.list_plugins()
print(names)  # ["greet", "calculator", "counter"]
```

### 生成工具规格

用于 LLM 工具调用：

```python
# 获取插件规格列表
specs = registry.to_specs()

# 结果格式
[
    {
        "name": "greet",
        "description": "Say hello to someone",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name to greet"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "calculator",
        "description": "Perform basic calculations",
        "parameters": {...}
    }
]
```

### 清理

```python
# 清理所有插件（调用每个插件的 teardown）
await registry.cleanup()

# 移除单个插件
registry.unregister("counter")
```

---

## 插件结果

### PluginResult 类

```python
class PluginResult:
    success: bool       # 是否成功
    output: Any         # 输出数据
    error: str | None   # 错误信息
    metadata: dict      # 元数据
```

### 创建结果

在插件内部使用辅助方法：

```python
class MyPlugin(BasePlugin):
    async def execute(self, **kwargs) -> PluginResult:
        # 成功结果
        return self.success("Operation completed")

        # 成功结果（带数据）
        return self.success({"id": 123, "status": "done"})

        # 成功结果（带元数据）
        return self.success(
            output="Processed",
            metadata={"duration_ms": 150, "cached": False}
        )

        # 失败结果
        return self.failure("Something went wrong")

        # 失败结果（带元数据）
        return self.failure(
            "Validation failed",
            metadata={"field": "email", "reason": "invalid format"}
        )
```

### 使用结果

```python
result = await registry.execute("my_plugin", data="test")

# 检查成功
if result.success:
    print(f"Output: {result.output}")
    print(f"Metadata: {result.metadata}")
else:
    print(f"Error: {result.output}")

# 布尔判断
if result:
    process(result.output)
```

### 合并结果

```python
# 并行执行多个插件
results = await asyncio.gather(
    registry.execute("plugin1", data="a"),
    registry.execute("plugin2", data="b"),
    registry.execute("plugin3", data="c"),
)

# 合并结果
combined = PluginResult.combine(results)

if combined.success:
    # 所有插件都成功
    print(combined.output)  # [result1.output, result2.output, result3.output]
else:
    # 至少一个失败
    print(combined.output)  # 包含错误信息
```

---

## 生命周期

### 生命周期方法

```python
class MyPlugin(BasePlugin):
    name: str = "my_plugin"

    async def setup(self) -> None:
        """
        初始化钩子。

        在插件注册到注册表时调用。
        用于：
        - 建立连接
        - 加载资源
        - 初始化状态
        """
        self._logger.info("Plugin initializing...")

    async def execute(self, **kwargs) -> PluginResult:
        """
        执行插件逻辑。

        每次调用插件时执行。
        """
        return self.success("Done")

    async def teardown(self) -> None:
        """
        清理钩子。

        在插件从注册表移除或注册表清理时调用。
        用于：
        - 关闭连接
        - 释放资源
        - 保存状态
        """
        self._logger.info("Plugin cleaning up...")
```

### 生命周期流程

```
1. 创建插件实例: plugin = MyPlugin()
2. 注册到注册表: registry.register(plugin)
   └── 调用 plugin.setup()
3. 执行插件: registry.execute("my_plugin", ...)
   └── 调用 plugin.execute(...)
4. 清理: registry.cleanup() 或 registry.unregister("my_plugin")
   └── 调用 plugin.teardown()
```

---

## 高级用法

### 参数规格定义

为 LLM 工具调用定义参数模式：

```python
class WeatherPlugin(BasePlugin):
    name: str = "get_weather"
    description: str = "Get current weather for a location"

    def get_parameters_schema(self) -> dict:
        """定义参数 JSON Schema"""
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name"
                },
                "units": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "default": "celsius",
                    "description": "Temperature units"
                }
            },
            "required": ["city"]
        }

    async def execute(self, city: str, units: str = "celsius", **kwargs) -> PluginResult:
        # 获取天气...
        return self.success(f"Weather in {city}: 20°{units[0].upper()}")
```

### 插件组合

```python
class PipelinePlugin(BasePlugin):
    """组合多个插件的管道"""

    name: str = "pipeline"
    description: str = "Execute multiple plugins in sequence"

    def __init__(self, registry: PluginRegistry, steps: list[str]):
        super().__init__()
        self._registry = registry
        self._steps = steps

    async def execute(self, data: Any, **kwargs) -> PluginResult:
        current = data

        for step in self._steps:
            result = await self._registry.execute(step, input=current, **kwargs)
            if not result.success:
                return result
            current = result.output

        return self.success(current)
```

### 插件装饰器

快速创建简单插件：

```python
from pycore.plugins import PluginRegistry

registry = PluginRegistry()

@registry.plugin(name="double", description="Double a number")
async def double_plugin(value: int, **kwargs):
    return value * 2

@registry.plugin(name="greet", description="Say hello")
async def greet_plugin(name: str, **kwargs):
    return f"Hello, {name}!"

# 使用
result = await registry.execute("double", value=5)
print(result.output)  # 10
```

### 错误处理

```python
class SafePlugin(BasePlugin):
    """带错误处理的插件"""

    name: str = "safe_plugin"

    async def execute(self, **kwargs) -> PluginResult:
        try:
            # 可能抛出异常的操作
            result = await risky_operation()
            return self.success(result)

        except ValueError as e:
            return self.failure(f"Invalid value: {e}")

        except ConnectionError as e:
            return self.failure(f"Connection failed: {e}")

        except Exception as e:
            # 记录意外错误
            self._logger.exception("Unexpected error")
            return self.failure(f"Unexpected error: {e}")
```

---

## 完整示例

```python
"""插件系统完整示例"""

import asyncio
from pycore.core import Logger, LoggerConfig, LogLevel
from pycore.plugins import BasePlugin, PluginResult, PluginRegistry

# 配置日志
logger = Logger.configure(LoggerConfig(level=LogLevel.DEBUG))

# 定义插件
class TextProcessorPlugin(BasePlugin):
    name: str = "text_processor"
    description: str = "Process text with various operations"

    async def execute(
        self,
        text: str,
        operation: str = "upper",
        **kwargs,
    ) -> PluginResult:
        operations = {
            "upper": str.upper,
            "lower": str.lower,
            "title": str.title,
            "reverse": lambda s: s[::-1],
        }

        if operation not in operations:
            return self.failure(f"Unknown operation: {operation}")

        result = operations[operation](text)
        return self.success(result, metadata={"original_length": len(text)})


class WordCountPlugin(BasePlugin):
    name: str = "word_count"
    description: str = "Count words in text"

    async def execute(self, text: str, **kwargs) -> PluginResult:
        words = text.split()
        return self.success({
            "word_count": len(words),
            "char_count": len(text),
            "words": words,
        })


async def main():
    # 创建注册表
    registry = PluginRegistry()

    # 注册插件
    registry.register(TextProcessorPlugin())
    registry.register(WordCountPlugin())

    logger.info(f"Registered plugins: {registry.list_plugins()}")

    # 测试文本处理
    text = "hello world from pycore"

    result = await registry.execute("text_processor", text=text, operation="upper")
    logger.info(f"Upper: {result.output}")

    result = await registry.execute("text_processor", text=text, operation="title")
    logger.info(f"Title: {result.output}")

    # 测试词数统计
    result = await registry.execute("word_count", text=text)
    logger.info(f"Word count: {result.output}")

    # 获取工具规格
    specs = registry.to_specs()
    logger.debug(f"Plugin specs: {specs}")

    # 清理
    await registry.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
```
