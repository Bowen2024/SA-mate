"""
路由工具和装饰器。

提供定义 API 路由的便捷模式。
"""

from functools import wraps
from typing import Any, Callable, Optional, Type, Union

from pydantic import BaseModel

# 尝试导入 FastAPI 依赖
try:
    from fastapi import APIRouter as FastAPIRouter
    from fastapi import Depends, HTTPException, Query, status
    from fastapi.responses import JSONResponse

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPIRouter = object

from pycore.api.responses import APIResponse, error_response, success_response
from pycore.core.logger import get_logger


class APIRouter:
    """
    具有标准化模式的增强 API 路由。

    用额外的便利功能包装 FastAPI 路由。

    用法：
        router = APIRouter(prefix="/users", tags=["users"])

        @router.get("/{user_id}")
        async def get_user(user_id: int):
            return {"id": user_id}

        # 注册到应用
        app.include_router(router.router)
    """

    def __init__(
        self,
        prefix: str = "",
        tags: list[str] = None,
        dependencies: list = None,
    ):
        if not FASTAPI_AVAILABLE:
            raise RuntimeError("FastAPI not installed. Install with: pip install pycore[api]")

        self.router = FastAPIRouter(
            prefix=prefix,
            tags=tags or [],
            dependencies=dependencies or [],
        )
        self._logger = get_logger()

    def get(self, path: str, **kwargs):
        """GET 路由装饰器。"""
        return self.router.get(path, **kwargs)

    def post(self, path: str, **kwargs):
        """POST 路由装饰器。"""
        return self.router.post(path, **kwargs)

    def put(self, path: str, **kwargs):
        """PUT 路由装饰器。"""
        return self.router.put(path, **kwargs)

    def delete(self, path: str, **kwargs):
        """DELETE 路由装饰器。"""
        return self.router.delete(path, **kwargs)

    def patch(self, path: str, **kwargs):
        """PATCH 路由装饰器。"""
        return self.router.patch(path, **kwargs)

    def add_api_route(self, path: str, endpoint: Callable, **kwargs):
        """以编程方式添加路由。"""
        self.router.add_api_route(path, endpoint, **kwargs)


def route(
    method: str = "GET",
    path: str = "/",
    response_model: Type[BaseModel] = None,
    status_code: int = 200,
    wrap_response: bool = True,
):
    """
    通用路由装饰器。

    用法：
        @route("POST", "/items", status_code=201)
        async def create_item(data: ItemCreate):
            return {"id": 1, **data.dict()}
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                if wrap_response:
                    return success_response(result)
                return result
            except HTTPException:
                raise
            except Exception as e:
                get_logger().exception(f"Route error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # 存储路由元数据
        wrapper._route_method = method
        wrapper._route_path = path
        wrapper._route_response_model = response_model
        wrapper._route_status_code = status_code

        return wrapper

    return decorator


def get(path: str = "/", **kwargs):
    """GET 路由装饰器。"""
    return route("GET", path, **kwargs)


def post(path: str = "/", status_code: int = 201, **kwargs):
    """POST 路由装饰器。"""
    return route("POST", path, status_code=status_code, **kwargs)


def put(path: str = "/", **kwargs):
    """PUT 路由装饰器。"""
    return route("PUT", path, **kwargs)


def delete(path: str = "/", status_code: int = 204, **kwargs):
    """DELETE 路由装饰器。"""
    return route("DELETE", path, status_code=status_code, **kwargs)


def handle_errors(func: Callable):
    """
    用于路由中标准化错误处理的装饰器。

    用法：
        @router.get("/items/{item_id}")
        @handle_errors
        async def get_item(item_id: int):
            item = await fetch_item(item_id)
            if not item:
                raise ValueError("Item not found")
            return item
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            get_logger().exception(f"Unhandled error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    return wrapper


class Pagination:
    """
    列表端点的分页依赖。

    用法：
        @router.get("/items")
        async def list_items(pagination: Pagination = Depends()):
            items = get_items(
                offset=pagination.offset,
                limit=pagination.limit
            )
            return items
    """

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页项目数"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size
