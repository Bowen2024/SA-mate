# 示例应用

本文档介绍 PyCore 框架的示例应用，包括 AI Agent 和 Web API。

## 目录

- [AI Agent 示例](#ai-agent-示例)
- [Web API 示例](#web-api-示例)
- [更多示例](#更多示例)

---

## AI Agent 示例

完整的 AI Agent 应用，展示如何组合 PyCore 的各个模块构建智能代理。

### 功能特点

- 使用 **服务层** (`BaseService`) 管理 Agent 生命周期
- 使用 **插件系统** (`PluginRegistry`) 注册工具
- 使用 **LLM 集成** (`OpenAIProvider`) 调用大模型
- 使用 **日志系统** 记录执行过程

### 运行方式

```bash
# 设置 API 密钥
export OPENAI_API_KEY=sk-...

# 可选：使用其他提供商
export OPENAI_BASE_URL=https://api.deepseek.com/v1

# 运行
python examples/agent_app/main.py "What is the capital of France?"
```

### 代码结构

```python
"""AI Agent 示例 - 简化版"""

import asyncio
from pycore.core import Logger, LoggerConfig, LogLevel
from pycore.plugins import BasePlugin, PluginResult, PluginRegistry
from pycore.services import BaseService
from pycore.integrations.llm import OpenAIProvider, Message, ToolDefinition

# 1. 定义工具插件
class CalculatorPlugin(BasePlugin):
    name: str = "calculator"
    description: str = "Perform math calculations"

    async def execute(self, expression: str, **kwargs) -> PluginResult:
        try:
            result = eval(expression)
            return self.success(f"Result: {result}")
        except Exception as e:
            return self.failure(str(e))

class WeatherPlugin(BasePlugin):
    name: str = "get_weather"
    description: str = "Get weather for a city"

    async def execute(self, city: str, **kwargs) -> PluginResult:
        # 模拟天气数据
        return self.success(f"Weather in {city}: 22°C, sunny")

# 2. 定义 Agent 服务
class AIAgent(BaseService):
    name: str = "ai_agent"
    max_steps: int = 10

    def __init__(self, llm, plugins, **data):
        super().__init__(**data)
        self.llm = llm
        self.plugins = plugins
        self._tools = self._build_tools()
        self._final_answer = None

    def _build_tools(self):
        """从插件构建工具定义"""
        return [
            ToolDefinition(
                name=spec["name"],
                description=spec["description"],
                parameters=spec.get("parameters", {"type": "object", "properties": {}})
            )
            for spec in self.plugins.to_specs()
        ]

    async def step(self) -> str:
        """执行一个 Agent 步骤"""
        # 构建消息
        messages = [Message.system("You are a helpful assistant.")]
        messages.extend(
            Message(role=m.role, content=m.content)
            for m in self.context.messages
        )

        # 调用 LLM
        response = await self.llm.chat(messages, tools=self._tools)

        if response.has_tool_calls:
            # 执行工具
            results = []
            for tool_call in response.tool_calls:
                args = json.loads(tool_call.arguments)
                input_val = next(iter(args.values())) if args else ""
                result = await self.plugins.execute(tool_call.name, input_val)
                results.append(f"{tool_call.name}: {result.output}")

            self.context.add_message("assistant", "Tool calls executed")
            self.context.add_message("user", "\n".join(results))
            return f"Executed {len(response.tool_calls)} tools"
        else:
            self._final_answer = response.content
            return "Got final answer"

    async def should_stop(self) -> bool:
        return self._final_answer is not None

# 3. 运行 Agent
async def main():
    logger = Logger.configure(LoggerConfig(level=LogLevel.INFO))

    # 创建 LLM
    llm = OpenAIProvider(api_key="sk-...", model="gpt-4o-mini")

    # 创建插件
    plugins = PluginRegistry()
    plugins.register(CalculatorPlugin())
    plugins.register(WeatherPlugin())

    # 创建 Agent
    agent = AIAgent(llm=llm, plugins=plugins)
    agent.context.add_message("user", "What is 15 * 24 and the weather in Tokyo?")

    # 运行
    await agent.run()
    print(f"Answer: {agent._final_answer}")

    await llm.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### 完整代码

完整代码见 `examples/agent_app/main.py`。

---

## Web API 示例

RESTful API 应用，展示 FastAPI 集成和标准化响应。

### 功能特点

- 使用 **API 层** (`APIServer`, `APIRouter`) 构建 REST API
- 使用 **中间件** 处理请求上下文和错误
- 使用 **插件系统** 封装业务逻辑
- 使用 **标准响应** 统一 API 格式

### 运行方式

```bash
# 安装依赖
pip install pycore[api]

# 运行
python examples/web_api/main.py

# 或使用 uvicorn
uvicorn examples.web_api.main:app --reload
```

### API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| GET | /docs | Swagger UI |
| GET | /items | 商品列表（分页） |
| GET | /items/{id} | 获取商品 |
| POST | /items | 创建商品 |
| PUT | /items/{id} | 更新商品 |
| DELETE | /items/{id} | 删除商品 |
| GET | /items/{id}/price | 计算价格 |

### 代码结构

```python
"""Web API 示例 - 简化版"""

from pydantic import BaseModel
from pycore.api import (
    APIServer,
    APIConfig,
    APIRouter,
    RequestContextMiddleware,
    success_response,
    error_response,
    paginated_response,
)
from pycore.plugins import BasePlugin, PluginResult, PluginRegistry

# 1. 数据模型
class ItemCreate(BaseModel):
    name: str
    price: float

# 2. 业务插件
class ValidatorPlugin(BasePlugin):
    name: str = "validator"
    description: str = "Validate item data"

    async def execute(self, item: ItemCreate, **kwargs) -> PluginResult:
        if not item.name or len(item.name) < 2:
            return self.failure("Name too short")
        if item.price < 0:
            return self.failure("Price must be positive")
        return self.success("Valid")

# 3. 存储
items_db = {}
next_id = 1

# 4. 路由
router = APIRouter(prefix="/items", tags=["items"])
plugins = PluginRegistry()
plugins.register(ValidatorPlugin())

@router.get("")
async def list_items(page: int = 1, page_size: int = 20):
    items = list(items_db.values())
    return paginated_response(
        data=items[(page-1)*page_size:page*page_size],
        page=page,
        page_size=page_size,
        total_items=len(items),
    )

@router.get("/{item_id}")
async def get_item(item_id: int):
    if item_id not in items_db:
        response, _ = error_response("Not found", "NOT_FOUND", 404)
        return response
    return success_response(items_db[item_id])

@router.post("")
async def create_item(data: ItemCreate):
    global next_id

    # 验证
    result = await plugins.execute("validator", data)
    if not result.success:
        response, _ = error_response(result.output, "VALIDATION_ERROR", 400)
        return response

    # 创建
    item = {"id": next_id, **data.dict()}
    items_db[next_id] = item
    next_id += 1

    return success_response(item, message="Created")

# 5. 服务器
server = APIServer(APIConfig(title="Items API", debug=True))
server.add_middleware(RequestContextMiddleware)
server.include_router(router)

# 初始数据
@server.on_startup
async def init():
    global next_id
    items_db[1] = {"id": 1, "name": "Widget", "price": 9.99}
    next_id = 2

app = server.app

if __name__ == "__main__":
    server.run()
```

### 测试命令

```bash
# 列表
curl http://localhost:8000/items

# 获取
curl http://localhost:8000/items/1

# 创建
curl -X POST http://localhost:8000/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Gadget","price":19.99}'

# 更新
curl -X PUT http://localhost:8000/items/1 \
  -H "Content-Type: application/json" \
  -d '{"name":"Super Widget"}'

# 删除
curl -X DELETE http://localhost:8000/items/1
```

### 响应示例

```json
// GET /items
{
  "success": true,
  "data": [
    {"id": 1, "name": "Widget", "price": 9.99}
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 1,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  }
}

// POST /items
{
  "success": true,
  "data": {"id": 2, "name": "Gadget", "price": 19.99},
  "message": "Created"
}

// GET /items/999
{
  "success": false,
  "error": "Not found",
  "error_code": "NOT_FOUND"
}
```

### 完整代码

完整代码见 `examples/web_api/main.py`。

---

## 更多示例

### CLI 应用

```python
"""CLI 工具示例"""

import asyncio
import argparse
from pycore.core import Logger, LoggerConfig, LogLevel
from pycore.plugins import PluginRegistry

# 注册命令插件
registry = PluginRegistry()

@registry.plugin(name="greet", description="Greet someone")
async def greet(name: str = "World", **kwargs):
    return f"Hello, {name}!"

@registry.plugin(name="calc", description="Calculate expression")
async def calc(expr: str, **kwargs):
    return eval(expr)

async def main():
    parser = argparse.ArgumentParser(description="PyCore CLI")
    parser.add_argument("command", help="Command to run")
    parser.add_argument("args", nargs="*", help="Command arguments")
    args = parser.parse_args()

    Logger.configure(LoggerConfig(level=LogLevel.INFO))

    # 解析参数为 kwargs
    kwargs = {}
    for arg in args.args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            kwargs[key] = value

    # 执行命令
    result = await registry.execute(args.command, **kwargs)
    print(result.output)

if __name__ == "__main__":
    asyncio.run(main())
```

运行：
```bash
python cli.py greet name=Alice
# Hello, Alice!

python cli.py calc expr="10 + 20"
# 30
```

### 数据管道

```python
"""数据处理管道示例"""

import asyncio
from pycore.execution import SequentialFlow, ParallelFlow

# 处理函数
async def load_data(source, **config):
    print(f"Loading from {source}...")
    return [{"id": i, "value": i * 10} for i in range(5)]

async def filter_data(data, **config):
    min_value = config.get("min_value", 0)
    return [d for d in data if d["value"] >= min_value]

async def transform_data(data, **config):
    return [{"id": d["id"], "value": d["value"] * 2} for d in data]

async def save_data(data, **config):
    print(f"Saving {len(data)} items...")
    return {"saved": len(data)}

async def main():
    # 创建管道
    pipeline = SequentialFlow(name="data_pipeline")
    pipeline.add_step("load", load_data, source="database")
    pipeline.add_step("filter", filter_data, min_value=20)
    pipeline.add_step("transform", transform_data)
    pipeline.add_step("save", save_data)

    # 运行
    result = await pipeline.run(None)

    if result.success:
        print(f"Pipeline completed: {result.output}")
    else:
        print(f"Pipeline failed: {result.error}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 微服务健康检查

```python
"""微服务健康检查示例"""

import asyncio
from pycore.execution import ParallelFlow

async def check_database(input_data, **config):
    await asyncio.sleep(0.1)  # 模拟检查
    return {"database": "healthy", "latency_ms": 15}

async def check_cache(input_data, **config):
    await asyncio.sleep(0.05)
    return {"cache": "healthy", "latency_ms": 5}

async def check_external_api(input_data, **config):
    await asyncio.sleep(0.2)
    return {"api": "healthy", "latency_ms": 200}

async def main():
    health_check = ParallelFlow(name="health_check")
    health_check.add_step("database", check_database)
    health_check.add_step("cache", check_cache)
    health_check.add_step("external_api", check_external_api)

    result = await health_check.run(None)

    status = {
        "healthy": result.success,
        "checks": result.step_results,
    }

    print(status)

if __name__ == "__main__":
    asyncio.run(main())
```

输出：
```python
{
    "healthy": True,
    "checks": {
        "database": {"database": "healthy", "latency_ms": 15},
        "cache": {"cache": "healthy", "latency_ms": 5},
        "external_api": {"api": "healthy", "latency_ms": 200}
    }
}
```
