# 核心模块

核心模块 (`pycore.core`) 提供框架的基础功能，包括配置管理、日志系统��异常体系和基础数据模型。

## 目录

- [配置系统](#配置系统)
- [日志系统](#日志系统)
- [异常体系](#异常体系)
- [基础模型](#基础模型)

---

## 配置系统

配置系统位于 `pycore.core.config`，提供：
- 线程安全的单例配置管理器
- Pydantic 模型验证
- TOML 配置文件加载
- 环境变量覆盖

### 导入

```python
from pycore.core import ConfigManager, BaseSettings
# 或
from pycore.core.config import ConfigManager, BaseSettings
```

### 定义配置模型

```python
from typing import Optional
from pycore.core import BaseSettings

class DatabaseSettings(BaseSettings):
    """数据库配置"""
    host: str = "localhost"
    port: int = 5432
    name: str = "mydb"
    user: str = "postgres"
    password: Optional[str] = None

class AppSettings(BaseSettings):
    """应用配置"""
    debug: bool = False
    secret_key: str = "change-me"
    database: DatabaseSettings = DatabaseSettings()
    allowed_hosts: list[str] = ["localhost"]
```

### 使用 ConfigManager

```python
from pycore.core import ConfigManager

# 获取配置管理器（单例模式）
config = ConfigManager()

# 方式1：直接设置配置对象
config.settings = AppSettings(debug=True)

# 方式2：从 TOML 文件加载
config.load(AppSettings, "config.toml")

# 方式3：从字典加载
config.load_from_dict(AppSettings, {
    "debug": True,
    "database": {"host": "db.example.com"}
})

# 访问配置
print(config.settings.debug)  # True
print(config.settings.database.host)  # "db.example.com"
```

### TOML 配置文件

```toml
# config.toml
debug = true
secret_key = "my-secret-key"
allowed_hosts = ["localhost", "example.com"]

[database]
host = "db.example.com"
port = 5432
name = "production"
user = "app_user"
password = "secret123"
```

### 配置 Profile

根据环境加载不同配置：

```python
import os

profile = os.environ.get("APP_PROFILE", "dev")
config.load(AppSettings, f"config/config.{profile}.toml")
```

文件结构：
```
config/
├── config.dev.toml    # 开发环境
├── config.test.toml   # 测试环境
└── config.prod.toml   # 生产环境
```

### 环境变量覆盖

使用 `PYCORE_` 前缀的环境变量可以覆盖配置：

```bash
export PYCORE_DEBUG=true
export PYCORE_DATABASE_HOST=new-host.example.com
```

---

## 日志系统

日志系统位于 `pycore.core.logger`，基于 loguru 构建，提供：
- 环境感知的输出格式（开发用彩色，生产用 JSON）
- 多输出目标（控制台 + 文件）
- 结构化日志
- 上下文绑定

### 导入

```python
from pycore.core import Logger, LoggerConfig, LogLevel, get_logger
# 或
from pycore.core.logger import Logger, LoggerConfig, LogLevel, get_logger
```

### LogLevel 枚举

```python
class LogLevel(str, Enum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
```

### 配置日志

```python
from pycore.core import Logger, LoggerConfig, LogLevel

# 基本配置
logger = Logger.configure(LoggerConfig(
    level=LogLevel.DEBUG,
    app_name="myapp",
))

# 完整配置
logger = Logger.configure(LoggerConfig(
    level=LogLevel.INFO,
    app_name="myapp",
    json_logs=True,            # 生产环境用 JSON 格式
    log_file="logs/app.log",   # 写入文件
    rotation="500 MB",         # 日志轮转
    retention="30 days",       # 保留时间
))
```

### 基本用法

```python
# 简单日志
logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
logger.critical("Critical message")

# 结构化日志（附加字段）
logger.info("User logged in", user_id=123, ip="192.168.1.1")
# 输出: 2024-01-01 12:00:00 | INFO | User logged in | user_id=123 ip=192.168.1.1

# 异常日志
try:
    risky_operation()
except Exception as e:
    logger.exception("Operation failed")
    # 自动包含完整堆栈跟踪
```

### 上下文绑定

创建带固定上下文的日志器：

```python
# 绑定请求上下文
request_logger = logger.bind(
    request_id="abc123",
    user_id=456,
    path="/api/users"
)

# 后续所有日志自动包含这些字段
request_logger.info("Processing request")
# 输出: ... | INFO | Processing request | request_id=abc123 user_id=456 path=/api/users

request_logger.debug("Fetching data")
# 输出: ... | DEBUG | Fetching data | request_id=abc123 user_id=456 path=/api/users

request_logger.info("Request completed", status=200)
# 输出: ... | INFO | Request completed | request_id=abc123 user_id=456 path=/api/users status=200
```

### 快捷函数

```python
from pycore.core import get_logger

# 获取已配置的日志器
logger = get_logger()
logger.info("Hello")
```

### 输出格式示例

开发环境（彩色）：
```
2024-01-01 12:00:00.123 | DEBUG | myapp | Debug message
2024-01-01 12:00:00.124 | INFO  | myapp | User logged in | user_id=123
2024-01-01 12:00:00.125 | ERROR | myapp | Operation failed
Traceback (most recent call last):
  ...
```

生产环境（JSON）：
```json
{"timestamp": "2024-01-01T12:00:00.123Z", "level": "INFO", "app": "myapp", "message": "User logged in", "user_id": 123}
```

---

## 异常体系

异常体系位于 `pycore.core.exceptions`，提供统一的异常层次结构。

### 异常层次

```
PyCoreError (基类)
├── ConfigurationError     # 配置相关错误
├── PluginError           # 插件相关错误
│   └── PluginNotFoundError  # 插件未找到
├── ServiceError          # 服务相关错误
│   └── ServiceStateError    # 服务状态错误
├── ExecutionError        # 执行相关错误
└── LLMError              # LLM 相关错误
    └── TokenLimitError      # Token 超限
```

### 导入

```python
from pycore.core.exceptions import (
    PyCoreError,
    ConfigurationError,
    PluginError,
    PluginNotFoundError,
    ServiceError,
    ServiceStateError,
    ExecutionError,
    LLMError,
    TokenLimitError,
)
```

### 基类 PyCoreError

所有 PyCore 异常的基类，支持附加详情：

```python
class PyCoreError(Exception):
    def __init__(self, message: str, **details):
        self.message = message
        self.details = details
        super().__init__(message)
```

### 使用示例

```python
# 抛出异常
raise ConfigurationError(
    "Invalid database configuration",
    key="database.host",
    value=None,
)

raise PluginNotFoundError(
    "Plugin not registered",
    plugin_name="unknown_plugin",
)

raise ServiceStateError(
    "Cannot start service from current state",
    service_name="my_service",
    from_state="ERROR",
    to_state="RUNNING",
)

raise TokenLimitError(
    "Context length exceeded",
    model="gpt-4",
    token_count=10000,
    limit=8192,
)
```

### 捕获和处理

```python
from pycore.core.exceptions import PyCoreError, PluginError, PluginNotFoundError

try:
    result = await registry.execute("unknown_plugin", data)
except PluginNotFoundError as e:
    # 特定异常
    logger.warning(f"Plugin not found: {e.details.get('plugin_name')}")
except PluginError as e:
    # 插件类异常
    logger.error(f"Plugin error: {e}")
except PyCoreError as e:
    # 所有 PyCore 异常
    logger.error(f"PyCore error: {e}", details=e.details)
```

---

## 基础模型

基础模型位于 `pycore.core.schema`，提供通用的数据结构。

### 导入

```python
from pycore.core import Result, Message, Metadata
# 或
from pycore.core.schema import Result, Message, Metadata
```

### Result[T] - 操作结果

泛型结果类型，用于表示操作的成功或失败：

```python
from pycore.core import Result

# 创建成功结果
result = Result.ok(data={"user_id": 123, "name": "Alice"})
print(result.success)  # True
print(result.data)     # {"user_id": 123, "name": "Alice"}
print(result.error)    # None

# 创建失败结果
result = Result.fail(error="User not found", code="USER_NOT_FOUND")
print(result.success)  # False
print(result.data)     # None
print(result.error)    # "User not found"
print(result.code)     # "USER_NOT_FOUND"

# 布尔判断
if result:
    process(result.data)
else:
    handle_error(result.error)
```

### Message - 消息模型

用于 LLM 对话和消息传递：

```python
from pycore.core import Message

# 直接创建
msg = Message(role="user", content="Hello, how are you?")

# 使用工厂方法
system_msg = Message.system("You are a helpful assistant.")
user_msg = Message.user("What is Python?")
assistant_msg = Message.assistant("Python is a programming language...")

# 转换为字典（用于 API 调用）
data = msg.to_dict()
# {"role": "user", "content": "Hello, how are you?"}

# 从字典创建
msg = Message.from_dict({"role": "user", "content": "Hello"})
```

### Metadata - 元数据

用于存储键值对元数据：

```python
from pycore.core import Metadata

meta = Metadata()
meta.set("created_at", "2024-01-01")
meta.set("author", "Alice")

print(meta.get("author"))  # "Alice"
print(meta.get("unknown", "default"))  # "default"

# 转换为字典
data = meta.to_dict()
# {"created_at": "2024-01-01", "author": "Alice"}
```

### Identifiable - 可标识基类

带有唯一 ID 的基类：

```python
from pycore.core.schema import Identifiable

class MyEntity(Identifiable):
    name: str
    value: int

entity = MyEntity(name="test", value=42)
print(entity.id)  # 自动生成的 UUID
```

---

## 完整示例

```python
"""核心模块完整示例"""

import asyncio
from pycore.core import (
    ConfigManager,
    BaseSettings,
    Logger,
    LoggerConfig,
    LogLevel,
    Result,
    Message,
)
from pycore.core.exceptions import ConfigurationError

# 1. 定义配置
class AppSettings(BaseSettings):
    app_name: str = "demo"
    debug: bool = False
    log_level: str = "INFO"

# 2. 加载配置
config = ConfigManager()
try:
    config.load_from_dict(AppSettings, {
        "app_name": "core_demo",
        "debug": True,
        "log_level": "DEBUG",
    })
except ConfigurationError as e:
    print(f"Configuration error: {e}")
    exit(1)

# 3. 配置日志
logger = Logger.configure(LoggerConfig(
    level=LogLevel[config.settings.log_level],
    app_name=config.settings.app_name,
    json_logs=not config.settings.debug,
))

# 4. 使用 Result
def divide(a: int, b: int) -> Result[float]:
    if b == 0:
        return Result.fail("Division by zero")
    return Result.ok(a / b)

# 5. 使用 Message
messages = [
    Message.system("You are a calculator."),
    Message.user("What is 10 / 2?"),
]

async def main():
    logger.info("Application started")

    # 测试 Result
    result = divide(10, 2)
    if result:
        logger.info(f"Result: {result.data}")
    else:
        logger.error(f"Error: {result.error}")

    result = divide(10, 0)
    if not result:
        logger.warning(f"Division failed: {result.error}")

    # 测试 Message
    for msg in messages:
        logger.debug(f"Message: {msg.to_dict()}")

    logger.info("Application finished")

if __name__ == "__main__":
    asyncio.run(main())
```
