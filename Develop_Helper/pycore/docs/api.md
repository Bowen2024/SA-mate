# API 层

API 层 (`pycore.api`) 提供 FastAPI 集成，包括服务器配置、路由、中间件和标准响应格式。

## 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [服务器配置](#服务器配置)
- [路由](#路由)
- [中间件](#中间件)
- [标准响应](#标准��应)
- [完整示例](#完整示例)

---

## 安装

API 层需要额外安装 FastAPI 依赖：

```bash
pip install pycore[api]
```

### 导入

```python
from pycore.api import (
    # 服务器
    APIServer,
    APIConfig,
    create_app,
    # 路由
    APIRouter,
    # 中间件
    RequestContextMiddleware,
    ErrorHandlerMiddleware,
    # 响应
    APIResponse,
    success_response,
    error_response,
    paginated_response,
)
```

---

## 快速开始

```python
from pycore.api import APIServer, APIConfig, APIRouter, success_response

# 创建路由
router = APIRouter(prefix="/api", tags=["api"])

@router.get("/hello")
async def hello():
    return success_response({"message": "Hello, World!"})

# 创建服务器
server = APIServer(APIConfig(
    title="My API",
    port=8000,
    debug=True,
))

# 注册路由
server.include_router(router)

# 运行
server.run()
```

---

## 服务器配置

### APIConfig

```python
from pycore.api import APIConfig

config = APIConfig(
    # 应用设置
    title="My API",
    description="API description",
    version="1.0.0",
    docs_url="/docs",          # Swagger UI
    redoc_url="/redoc",        # ReDoc
    openapi_url="/openapi.json",

    # 服务器设置
    host="0.0.0.0",
    port=8000,
    debug=True,                # True 时启用文档
    reload=False,              # 自动重载
    workers=1,                 # 工作进程数

    # CORS 设置
    cors_enabled=True,
    cors_origins=["*"],
    cors_methods=["*"],
    cors_headers=["*"],
)
```

### APIServer

```python
from pycore.api import APIServer, APIConfig

# 创建服务器
server = APIServer(APIConfig(title="My API"))

# 获取 FastAPI 应用实例
app = server.app

# 添加路由
server.include_router(router)

# 添加中间件
server.add_middleware(SomeMiddleware, option=value)

# 生命周期钩子
@server.on_startup
async def init_db():
    await database.connect()

@server.on_shutdown
async def close_db():
    await database.disconnect()

# 同步运行
server.run()

# 异步运行
await server.serve()
```

### 应用工厂

```python
from pycore.api import create_app

# 快速创建应用
app = create_app(
    title="My API",
    version="1.0.0",
    debug=True,
)

@app.get("/")
async def root():
    return {"message": "Hello"}

# 用于 uvicorn
# uvicorn main:app --reload
```

---

## 路由

### APIRouter

```python
from pycore.api import APIRouter

# 创建路由器
router = APIRouter(
    prefix="/users",
    tags=["users"],
)

# 定义路由
@router.get("")
async def list_users():
    return {"users": []}

@router.get("/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id}

@router.post("")
async def create_user(data: UserCreate):
    return {"id": 1, **data.dict()}

@router.put("/{user_id}")
async def update_user(user_id: int, data: UserUpdate):
    return {"id": user_id, **data.dict()}

@router.delete("/{user_id}")
async def delete_user(user_id: int):
    return {"deleted": True}

# 注册到服务器
server.include_router(router)
```

### 分页依赖

```python
from pycore.api.routes import Pagination
from fastapi import Depends

@router.get("/items")
async def list_items(pagination: Pagination = Depends()):
    items = await get_items(
        offset=pagination.offset,
        limit=pagination.limit,
    )
    total = await count_items()

    return paginated_response(
        data=items,
        page=pagination.page,
        page_size=pagination.page_size,
        total_items=total,
    )
```

---

## 中间件

### RequestContextMiddleware

自动设置请求上下文：

```python
from pycore.api import RequestContextMiddleware
from pycore.execution import ExecutionContext

server.add_middleware(RequestContextMiddleware)

@router.get("/test")
async def test():
    # 自动可用的上下文
    request_id = ExecutionContext.get("request_id")
    method = ExecutionContext.get("method")
    path = ExecutionContext.get("path")

    return {"request_id": request_id}
```

设置的上下文变量：
- `request_id`: 请求 ID（来自 X-Request-ID 或自动生成）
- `method`: HTTP 方法
- `path`: 请求路径
- `start_time`: 请求开始时间

响应头：
- `X-Request-ID`: 请求 ID
- `X-Response-Time`: 响应时间

### ErrorHandlerMiddleware

统一错误处理：

```python
from pycore.api import ErrorHandlerMiddleware

server.add_middleware(ErrorHandlerMiddleware, debug=True)

# 未捕获的异常会返回标准错误响应
# {
#     "success": false,
#     "error": "Error message",
#     "error_code": "INTERNAL_ERROR",
#     "request_id": "..."
# }
```

### CORS 配置

```python
from pycore.api.middleware import CORSMiddleware
from fastapi.middleware.cors import CORSMiddleware as FastAPICORS

# 开发环境（允许所有）
server.app.add_middleware(FastAPICORS, **CORSMiddleware.permissive())

# 生产环境（限制来源）
server.app.add_middleware(
    FastAPICORS,
    **CORSMiddleware.restricted(
        origins=["https://example.com", "https://app.example.com"],
        methods=["GET", "POST", "PUT", "DELETE"],
        headers=["Authorization", "Content-Type"],
    )
)
```

---

## 标准响应

### 响应格式

```python
# 成功响应
{
    "success": true,
    "data": {...},
    "message": "Optional message",
    "timestamp": "2024-01-01T12:00:00",
    "request_id": "abc123",
    "metadata": {}
}

# 错误响应
{
    "success": false,
    "error": "Error description",
    "error_code": "ERROR_CODE",
    "timestamp": "2024-01-01T12:00:00",
    "request_id": "abc123"
}

# 分页响应
{
    "success": true,
    "data": [...],
    "pagination": {
        "page": 1,
        "page_size": 20,
        "total_items": 100,
        "total_pages": 5,
        "has_next": true,
        "has_prev": false
    }
}
```

### 使用响应工具

```python
from pycore.api import success_response, error_response, paginated_response
from pycore.execution import ExecutionContext

@router.get("/{item_id}")
async def get_item(item_id: int):
    item = await find_item(item_id)

    if not item:
        response, _ = error_response(
            error="Item not found",
            error_code="ITEM_NOT_FOUND",
            status_code=404,
            request_id=ExecutionContext.get("request_id"),
        )
        return response

    return success_response(
        data=item,
        message="Item retrieved",
        request_id=ExecutionContext.get("request_id"),
    )

@router.get("")
async def list_items(page: int = 1, page_size: int = 20):
    items = await get_items(page, page_size)
    total = await count_items()

    return paginated_response(
        data=items,
        page=page,
        page_size=page_size,
        total_items=total,
        request_id=ExecutionContext.get("request_id"),
    )
```

---

## 完整示例

```python
"""完整 API 示例"""

from pydantic import BaseModel
from pycore.core import Logger, LoggerConfig, LogLevel
from pycore.api import (
    APIServer,
    APIConfig,
    APIRouter,
    RequestContextMiddleware,
    ErrorHandlerMiddleware,
    success_response,
    error_response,
    paginated_response,
)
from pycore.execution import ExecutionContext

# 配置日志
Logger.configure(LoggerConfig(level=LogLevel.DEBUG))

# 数据模型
class ItemCreate(BaseModel):
    name: str
    price: float

class ItemUpdate(BaseModel):
    name: str = None
    price: float = None

# 模拟数据库
items_db = {}
next_id = 1

# 路由
router = APIRouter(prefix="/items", tags=["items"])

@router.get("")
async def list_items(page: int = 1, page_size: int = 20):
    items = list(items_db.values())
    start = (page - 1) * page_size
    end = start + page_size

    return paginated_response(
        data=items[start:end],
        page=page,
        page_size=page_size,
        total_items=len(items),
        request_id=ExecutionContext.get("request_id"),
    )

@router.get("/{item_id}")
async def get_item(item_id: int):
    if item_id not in items_db:
        response, _ = error_response("Item not found", "NOT_FOUND", 404)
        return response

    return success_response(items_db[item_id])

@router.post("")
async def create_item(data: ItemCreate):
    global next_id
    item = {"id": next_id, **data.dict()}
    items_db[next_id] = item
    next_id += 1

    return success_response(item, message="Item created")

@router.put("/{item_id}")
async def update_item(item_id: int, data: ItemUpdate):
    if item_id not in items_db:
        response, _ = error_response("Item not found", "NOT_FOUND", 404)
        return response

    item = items_db[item_id]
    if data.name:
        item["name"] = data.name
    if data.price:
        item["price"] = data.price

    return success_response(item, message="Item updated")

@router.delete("/{item_id}")
async def delete_item(item_id: int):
    if item_id not in items_db:
        response, _ = error_response("Item not found", "NOT_FOUND", 404)
        return response

    del items_db[item_id]
    return success_response(message="Item deleted")

# 创建服务器
server = APIServer(APIConfig(
    title="Items API",
    version="1.0.0",
    debug=True,
))

# 添加中间件
server.add_middleware(RequestContextMiddleware)
server.add_middleware(ErrorHandlerMiddleware, debug=True)

# 注册路由
server.include_router(router)

# 初始化数据
@server.on_startup
async def init_data():
    global next_id
    items_db[1] = {"id": 1, "name": "Widget", "price": 9.99}
    items_db[2] = {"id": 2, "name": "Gadget", "price": 19.99}
    next_id = 3

if __name__ == "__main__":
    server.run()
```

运行后访问：
- http://localhost:8000/docs - Swagger UI
- http://localhost:8000/health - 健康检查
- http://localhost:8000/items - 商品列表
