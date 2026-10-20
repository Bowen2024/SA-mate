# PyCore Plugin 层规范（default）

> 来源：原 dev-standards/backend-plugin.md 原样迁移；外部服务调用安全条款消双写至 `shared/security.md`（本件留指针）；「深入阅读」节删除（指 pycore/docs，与禁读矛盾）。

> **仅用于 AI Agent 应用。** 普通业务系统不需要 Plugin 层。

## 架构选择

| 应用类型 | 调用链 |
|---------|--------|
| 普通业务系统 | Router → Service → Repository |
| AI Agent 应用 | Router → PluginRegistry → Plugin → Service |

## BasePlugin 速查

```python
from pycore.plugins import BasePlugin, PluginResult
from pycore.core import get_logger

logger = get_logger()  # 模块级！BasePlugin 没有内置 logger

class SearchPlugin(BasePlugin):
    name: str = "search_knowledge"
    description: str = "Search the knowledge base"
    parameters: dict = { ... }  # OpenAI function calling JSON Schema

    async def execute(self, query: str, limit: int = 5, **kwargs) -> PluginResult:
        # **kwargs 是必须的！
        try:
            results = await self._do_search(query, limit)
            return self.success({"query": query, "results": results})
        except Exception as e:
            return self.fail(f"Search error: {e}")
```

## PluginResult 速查

```python
result = PluginResult.ok(data)      # 成功
result = PluginResult.fail("msg")   # 失败

if not result:          # 用 __bool__ 判断
    msg = result.error  # 失败用 .error
else:
    data = result.data  # 成功用 .data
```

## PluginRegistry 速查

```python
registry = PluginRegistry()
registry.register(SearchPlugin())
result = await registry.execute("search_knowledge", query="Python")
specs = registry.to_specs()  # OpenAI function calling 格式
```

## 易错点

| 错误写法 | 正确写法 |
|---------|---------|
| `if not result.success:` | `if not result:` |
| `result.output`（取错误时）| `result.error` |
| `self.failure("msg")` | `self.fail("msg")` |
| `async def execute(self, x):` | `async def execute(self, x, **kwargs):` |
| `len(registry._plugins)` | `len(registry)` |

## 外部服务调用规则（强制）

### 按授权核对外部响应

封装第三方 API 时先核对官方文档和技术方案的响应契约。真实调用仅在已授权用途、额度及配置范围内执行；只有 Key 不代表已获付费授权。
已获授权时，使用最小必要调用确认响应结构，日志只保存状态码、字段名等必要脱敏信息，不 dump 响应全文或秘密。
授权或配置不足时，将受影响的真实联调交回编排器；已允许 Mock 的部分可按契约验证，但不得报告真实调用通过。

### 安全红线（指针）

- 百炼禁官方 SDK、`trust_env=False`、禁止继承环境变量：单一权威源在 `shared/security.md`「外部服务调用红线」，本件不重复展开。
