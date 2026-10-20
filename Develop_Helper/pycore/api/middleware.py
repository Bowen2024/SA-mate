"""
API 中间件组件。

提供请求上下文、错误处理和其他横切关注点。
"""

import time
import uuid
from typing import Callable

from pycore.core.logger import get_logger
from pycore.execution.context import ExecutionContext

# 尝试导入 FastAPI 依赖
try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    BaseHTTPMiddleware = object
    Request = object
    Response = object


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    设置请求上下文的中间件。

    将 request_id 和其他元数据添加到执行上下文，
    以便在整个请求生命周期中使用。

    用法：
        app.add_middleware(RequestContextMiddleware)

        # 在处理器中：
        request_id = ExecutionContext.get("request_id")
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not FASTAPI_AVAILABLE:
            raise RuntimeError("FastAPI not installed. Install with: pip install pycore[api]")

        # 生成请求 ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start_time = time.time()

        # 设置执行上下文
        async with ExecutionContext.scope(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            start_time=start_time,
        ):
            # 处理请求
            response = await call_next(request)

            # 添加响应头
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{(time.time() - start_time) * 1000:.2f}ms"

            return response


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    用于集中错误处理的中间件。

    捕获异常并返回标准化的错误响应。

    用法：
        app.add_middleware(ErrorHandlerMiddleware, debug=False)
    """

    def __init__(self, app, debug: bool = False):
        if not FASTAPI_AVAILABLE:
            raise RuntimeError("FastAPI not installed. Install with: pip install pycore[api]")
        super().__init__(app)
        self.debug = debug
        self._logger = get_logger()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)

        except Exception as e:
            request_id = ExecutionContext.get("request_id", "unknown")
            self._logger.exception(
                f"Unhandled exception: {e}",
                request_id=request_id,
                path=request.url.path,
            )

            # 构建错误响应
            error_body = {
                "success": False,
                "error": str(e) if self.debug else "Internal server error",
                "error_code": "INTERNAL_ERROR",
                "request_id": request_id,
            }

            if self.debug:
                error_body["error_type"] = type(e).__name__

            return JSONResponse(
                status_code=500,
                content=error_body,
            )


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    用于请求/响应日志记录的中间件。

    记录请求详情和响应状态。

    用法：
        app.add_middleware(LoggingMiddleware)
    """

    def __init__(self, app, log_body: bool = False):
        if not FASTAPI_AVAILABLE:
            raise RuntimeError("FastAPI not installed. Install with: pip install pycore[api]")
        super().__init__(app)
        self.log_body = log_body
        self._logger = get_logger()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 记录请求
        self._logger.info(
            f"Request: {request.method} {request.url.path}",
            method=request.method,
            path=request.url.path,
            query=str(request.query_params),
        )

        # 处理请求
        start_time = time.time()
        response = await call_next(request)
        duration = (time.time() - start_time) * 1000

        # 记录响应
        self._logger.info(
            f"Response: {response.status_code} ({duration:.2f}ms)",
            status_code=response.status_code,
            duration_ms=duration,
        )

        return response


class CORSMiddleware:
    """
    简单的 CORS 中间件配置辅助器。

    用法：
        from fastapi.middleware.cors import CORSMiddleware as FastAPICORS

        app.add_middleware(
            FastAPICORS,
            **CORSMiddleware.permissive()
        )
    """

    @staticmethod
    def permissive() -> dict:
        """用于开发的宽松 CORS 设置。"""
        return {
            "allow_origins": ["*"],
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }

    @staticmethod
    def restricted(
        origins: list[str],
        methods: list[str] = None,
        headers: list[str] = None,
    ) -> dict:
        """用于生产的受限 CORS 设置。"""
        return {
            "allow_origins": origins,
            "allow_credentials": True,
            "allow_methods": methods or ["GET", "POST", "PUT", "DELETE"],
            "allow_headers": headers or ["Authorization", "Content-Type"],
        }
