# 快速入门

本文档帮助你快速上手 PyCore 框架。

## 目录

- [安装](#安装)
- [五分钟教程](#五分钟教程)
- [项目结构](#项目结构)
- [下一步](#下一步)

---

## 安装

### 使用 pip 安装

```bash
# 核心功能（配置、日志、插件、服务、执行）
pip install pycore

# API 支持（FastAPI + uvicorn）
pip install pycore[api]

# LLM 集成（OpenAI + tiktoken）
pip install pycore[llm]

# 全部功能
pip install pycore[all]

# 开发依赖（pytest、black、mypy 等）
pip install pycore[dev]
```

### 开发模式安装

```bash
git clone <repo>
cd pycore
pip install -e ".[dev]"
```

### 依赖说明

| 安装选项 | 包含的依赖 |
|----------|-----------|
| 核心 | pydantic>=2.0, loguru>=0.7, tomli>=2.0 |
| `[api]` | fastapi>=0.100, uvicorn>=0.20 |
| `[llm]` | openai>=1.0, tiktoken>=0.5, tenacity>=8.0 |
| `[dev]` | pytest, pytest-asyncio, black, mypy, ruff |

---

## 五分钟教程

### 1. 配置日志

```python
from pycore.core import Logger, LoggerConfig, LogLevel

# 配置日志系统
logger = Logger.configure(LoggerConfig(
    level=LogLevel.DEBUG,
    app_name="myapp",
    json_logs=False,  # 开发环境用彩色输出
))

logger.info("Application started")
logger.debug("Debug info", key="value")
```

### 2. 创建插件

```python
from pycore.plugins import BasePlugin, PluginResult, PluginRegistry

class GreetPlugin(BasePlugin):
    """问候插件"""
    name: str = "greet"
    description: str = "Say hello to someone"

    async def execute(self, name: str, **kwargs) -> PluginResult:
        return self.success(f"Hello, {name}!")

# 注册插件
registry = PluginRegistry()
registry.register(GreetPlugin())
```

### 3. 执行插件

```python
import asyncio

async def main():
    result = await registry.execute("greet", "World")

    if result.success:
        print(result.output)  # "Hello, World!"
    else:
        print(f"Error: {result.output}")

asyncio.run(main())
```

### 4. 完整示例

```python
"""完整的 PyCore 入门示例"""

import asyncio
from pycore.core import Logger, LoggerConfig, LogLevel
from pycore.plugins import BasePlugin, PluginResult, PluginRegistry

# 配置日志
logger = Logger.configure(LoggerConfig(
    level=LogLevel.INFO,
    app_name="quickstart",
))

# 定义插件
class CalculatorPlugin(BasePlugin):
    name: str = "calculator"
    description: str = "Simple calculator"

    async def execute(self, a: int, b: int, op: str = "add", **kwargs) -> PluginResult:
        if op == "add":
            return self.success(a + b)
        elif op == "sub":
            return self.success(a - b)
        elif op == "mul":
            return self.success(a * b)
        elif op == "div":
            if b == 0:
                return self.failure("Division by zero")
            return self.success(a / b)
        else:
            return self.failure(f"Unknown operation: {op}")

async def main():
    # 创建注册表
    registry = PluginRegistry()
    registry.register(CalculatorPlugin())

    logger.info("Calculator plugin registered")

    # 执行计算
    result = await registry.execute("calculator", a=10, b=5, op="add")
    logger.info(f"10 + 5 = {result.output}")

    result = await registry.execute("calculator", a=10, b=5, op="mul")
    logger.info(f"10 * 5 = {result.output}")

    result = await registry.execute("calculator", a=10, b=0, op="div")
    if not result.success:
        logger.warning(f"Error: {result.output}")

if __name__ == "__main__":
    asyncio.run(main())
```

运行：
```bash
python quickstart.py
```

输出：
```
2024-01-01 12:00:00 | INFO | Calculator plugin registered
2024-01-01 12:00:00 | INFO | 10 + 5 = 15
2024-01-01 12:00:00 | INFO | 10 * 5 = 50
2024-01-01 12:00:00 | WARNING | Error: Division by zero
```

---

## 项目结构

### 典型项目布局

```
myproject/
├── config/
│   ├── config.toml          # 默认配置
│   ├── config.dev.toml      # 开发环境配置
│   └── config.prod.toml     # 生产环境配置
├── src/
│   ├── __init__.py
│   ├── plugins/             # 自定义插件
│   │   ├── __init__.py
│   │   └── my_plugin.py
│   ├── services/            # 自定义服务
│   │   ├── __init__.py
│   │   └── my_service.py
│   └── main.py              # 入口文件
├── tests/
│   └── test_plugins.py
├── pyproject.toml
└── README.md
```

### 入口文件示例

```python
# src/main.py
import asyncio
import os

from pycore.core import ConfigManager, BaseSettings, Logger, LoggerConfig, LogLevel

class AppSettings(BaseSettings):
    debug: bool = False
    log_level: str = "INFO"

async def main():
    # 加载配置
    profile = os.environ.get("APP_PROFILE", "dev")
    config = ConfigManager()
    config.load(AppSettings, f"config/config.{profile}.toml")

    # 配置日志
    level = LogLevel[config.settings.log_level]
    logger = Logger.configure(LoggerConfig(
        level=level,
        app_name="myapp",
        json_logs=not config.settings.debug,
    ))

    logger.info(f"Starting application in {profile} mode")

    # 应用逻辑...

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 下一步

根据你的需求，继续阅读相关文档：

| 需求 | 文档 |
|------|------|
| 深入了解配置、日志 | [核心模块](core.md) |
| 创建可扩展的工具 | [插件系统](plugins.md) |
| 构建有状态服务 | [服务层](services.md) |
| 流程编排和上下文 | [执行层](execution.md) |
| 构建 REST API | [API 层](api.md) |
| 集成 LLM（GPT/DeepSeek） | [LLM 集成](llm.md) |
| 查看完整示例 | [示例应用](examples.md) |
