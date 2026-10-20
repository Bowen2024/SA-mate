# PyCore Core 开发规范

## Logger 使用

```python
from pycore.core.logger import Logger, LoggerConfig, LogLevel, get_logger

# 应用启动时配置一次
Logger.configure(LoggerConfig(
    level=LogLevel.INFO,
    app_name="myapp",
    json_format=False,  # 生产环境用 True
))

# 在任何地方获取 logger（模块级）
logger = get_logger()
logger.info("Application started")
```

**注意**：使用 `get_logger()` 函数，不是 `Logger.get_logger()`。

## 异常处理规范

根据场景选择正确的错误处理方式：

| 场景 | 使用方式 | 示例 |
|------|---------|------|
| Plugin 业务错误 | `return self.fail()` | 密码错误、验证失败 |
| 系统级错误 | `raise XxxError()` | 数据库连接失败 |
| 路由层直接返回 | `error_response()` | 资源未找到(404) |

```python
# 系统级错误
from pycore.core.exceptions import ConfigurationError

def load_config():
    if not config_file.exists():
        raise ConfigurationError("配置文件不存在")  # 系统错误
```

## ConfigManager 使用规范

### 核心要点

1. **`load()` 返回 ConfigManager 本身**，通过 `.settings` 访问配置对象
2. **不支持 `section` 参数**，TOML section 作为嵌套字典处理
3. **`profile` 参数用于环境切换**（dev/prod），不是读取 section

```python
# 正确用法
config = ConfigManager()
config.load(AppSettings, "config.toml")
settings = config.settings  # 通过 .settings 获取配置对象
```

### 处理多 section 的 TOML 文件

**方案 A：定义扁平的 Settings（推荐简单场景）**

```toml
# config.toml（扁平结构）
debug = true
database_url = "sqlite:///app.db"
host = "localhost"
port = 8000
```

```python
class AppSettings(BaseSettings):
    debug: bool = False
    database_url: str
    host: str = "localhost"
    port: int = 8000

config = ConfigManager()
config.load(AppSettings, "config.toml")
settings = config.settings
```

**方案 B：定义嵌套的 Settings（推荐复杂场景）**

```toml
# config.toml（嵌套结构）
[app]
debug = true
title = "My App"

[database]
url = "sqlite:///app.db"

[server]
host = "localhost"
port = 8000
```

```python
class DatabaseSettings(BaseSettings):
    url: str

class ServerSettings(BaseSettings):
    host: str = "localhost"
    port: int = 8000

class AppSettings(BaseSettings):
    debug: bool = False
    title: str = "App"

class Settings(BaseSettings):
    app: AppSettings = AppSettings()
    database: DatabaseSettings
    server: ServerSettings = ServerSettings()

config = ConfigManager()
config.load(Settings, "config.toml")
settings = config.settings
print(settings.database.url)  # sqlite:///app.db
```

**方案 C：使用 raw 字典访问（绕过类型验证）**

```python
config = ConfigManager()
config.load(AppSettings, "config.toml")  # 仍需提供一个 Settings 类
raw = config.raw  # 获取原始字典
db_url = raw["database"]["url"]  # 直接访问
```

**方案 D：直接使用 tomllib（绕过 ConfigManager）**

```python
import tomllib

with open("config.toml", "rb") as f:
    config = tomllib.load(f)
db_settings = DatabaseSettings(**config.get("database", {}))
```

## TOML 配置文件规范

### 核心规则

1. **不支持表达式**：直接写计算结果，用注释说明
   ```toml
   token_expire_minutes = 10080  # 7天 (60 * 24 * 7)
   ```

2. **数据库密码特殊字符必须 URL 编码**：
   | 字符 | 编码 |
   |------|------|
   | `@` | `%40` |
   | `:` | `%3A` |
   | `#` | `%23` |

   ```toml
   # 密码 "Pass@123" 中的 @ 编码为 %40
   url = "mysql+pymysql://root:Pass%40123@localhost:3306/db"
   ```
