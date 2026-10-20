# PyCore 开发规范

本目录包含 PyCore 框架的开发规范文档。

## 规范列表

| 规范 | 描述 |
|------|------|
| [API 开发规范](api.md) | FastAPI 路由、参数、认证 |
| [Core 开发规范](core.md) | Logger、Config、异常处理 |
| [Plugins 开发规范](plugins.md) | 插件开发、Result 使用 |
| [Services 开发规范](services.md) | 服务层架构、Repository |

## 通用规范

### Result 类型使用

所有 Result 类型统一使用 `ok()/fail()` 工厂方法，数据字段统一为 `data`：

```python
from pycore.core import Result
from pycore.plugins import PluginResult
from pycore.execution import FlowResult

# 创建成功结果
result = Result.ok(data)
result = PluginResult.ok(output_data)
result = FlowResult.ok(data)

# 创建失败结果
result = Result.fail("error message")
result = PluginResult.fail("error message")
result = FlowResult.fail("error message")

# 检查结果（使用 __bool__）
if result:
    print(result.data)
else:
    print(result.error)
```

### 服务层选择

PyCore 提供三层服务架构，根据需求选择：

| 服务类型 | 使用场景 | 特点 |
|---------|---------|------|
| `SimpleService` | 简单 CRUD、无状态服务 | 无状态机 |
| `BaseService` | 需要基本生命周期管理 | 3 状态简化版 |
| `AgentService` | AI Agent、长期运行、对话服务 | 完整 7 状态 + 卡死检测 |

```python
from pycore.services import SimpleService, BaseService, AgentService

# 简单服务
class UserService(SimpleService):
    name: str = "user_service"

    async def get_user(self, user_id: int):
        ...

# 需要生命周期管理
class DataProcessor(BaseService):
    name: str = "processor"

    async def process(self, data):
        ...

# AI Agent 服务
class ChatAgent(AgentService):
    name: str = "chat_agent"

    async def step(self):
        ...
```

### 架构选择指南

| 应用类型 | 架构 | 说明 |
|---------|------|------|
| 普通业务系统 | Router → Service → Repository | 不需要 Plugin |
| AI Agent 应用 | Router → Plugin → Service | Plugin 作为 LLM 工具 |
