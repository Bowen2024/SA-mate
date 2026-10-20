# PyCore Plugins 开发规范

## Plugin 开发

```python
from pycore.plugins import BasePlugin, PluginResult
from pycore.core import get_logger

logger = get_logger()  # 模块级，BasePlugin 没有内置 logger

class MyPlugin(BasePlugin):
    name: str = "my_plugin"
    description: str = "插件描述"

    async def execute(self, param: str, **kwargs) -> PluginResult:
        # **kwargs 必须保留
        logger.info("Executing", param=param)
        if error_condition:
            return self.fail("错误信息")
        return self.ok(result_data)  # 使用 ok() 方法
```

## PluginResult 使用

### 创建结果

```python
# 成功结果
result = PluginResult.ok(data)
result = self.ok(data)  # BasePlugin 便捷方法

# 失败结果
result = PluginResult.fail("错误信息")
result = self.fail("错误信息")  # BasePlugin 便捷方法
```

### 检查结果

```python
result = await plugins.execute("my_plugin", **args)

# 使用 __bool__ 判断（推荐）
if not result:
    error_msg = result.error  # 失败时用 .error
else:
    data = result.data  # 成功时用 .data
```

### 向后兼容

为了向后兼容，以下别名仍然有效：

```python
# 这些仍然可用，但不推荐
result = PluginResult.success(data)  # 别名，等同于 ok()
result = self.success(data)          # 别名，等同于 ok()
value = result.output                # 别名，等同于 data
```

## Plugin vs Service 使用边界

**根据应用类型选择架构**：

| 应用类型 | 架构选择 | 说明 |
|---------|---------|------|
| 普通业务系统（无 AI 功能）| Router → Service → Repository | 不需要 Plugin 层 |
| AI Agent 应用（有对话/智能功能）| Router → Plugin → Service | Plugin 作为 LLM 可调用的工具 |

### 什么时候用 Plugin

- LLM 需要调用的工具（自动转换为 function calling 格式）
- 功能单一、可复用、无状态
- 例如：数据验证、密码加密、调用第三方 API

### 什么时候用 Service

- 需要多步骤编排
- 需要维护状态/上下文
- 复杂业务流程
- 例如：用户注册流程、订单处理流程

## 错误处理规范（Plugin 内）

```python
# Plugin 内的业务逻辑错误使用 return self.fail()
class PasswordValidator(BasePlugin):
    name: str = "password_validator"
    description: str = "验证密码强度"

    async def execute(self, password: str, **kwargs):
        if len(password) < 6:
            return self.fail("密码长度不足")  # 业务错误
        if not any(c.isupper() for c in password):
            return self.fail("密码需要包含大写字母")
        return self.ok(True)
```

## Plugin 注册和执行

```python
from pycore.plugins import PluginRegistry

# 创建注册表
registry = PluginRegistry()

# 注册插件
registry.register(MyPlugin())
registry.register(PasswordValidator())

# 执行插件
result = await registry.execute("my_plugin", param="value")

# 批量执行
results = await registry.execute_many([
    ("plugin1", {"arg1": "value1"}),
    ("plugin2", {"arg2": "value2"}),
])

# 获取 OpenAI function calling 格式
specs = registry.to_specs()
```
