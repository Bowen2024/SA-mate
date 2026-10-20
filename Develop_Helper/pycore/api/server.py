"""
FastAPI 服务器集成。

提供应用工厂和服务器配置。
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from pycore.core.logger import get_logger

# 尝试导入 FastAPI 依赖
try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = None

# 尝试导入 uvicorn
try:
    import uvicorn

    UVICORN_AVAILABLE = True
except ImportError:
    UVICORN_AVAILABLE = False


class APIConfig(BaseModel):
    """
    API 服务器配置。

    用法：
        config = APIConfig(
            title="My API",
            host="0.0.0.0",
            port=8080,
            debug=True
        )
    """

    # 应用设置
    title: str = "PyCore API"
    description: str = ""
    version: str = "1.0.0"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"
    openapi_url: str = "/openapi.json"

    # 服务器设置
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    reload: bool = False
    workers: int = 1

    # CORS 设置
    cors_enabled: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_headers: list[str] = Field(default_factory=lambda: ["*"])

    # 生命周期
    startup_handlers: list[Callable] = Field(default_factory=list)
    shutdown_handlers: list[Callable] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


class APIServer:
    """
    FastAPI 服务器包装器。

    提供创建和运行 FastAPI 应用的便捷方法。

    用法：
        # 创建服务器
        server = APIServer(APIConfig(title="My API"))

        # 添加路由
        server.include_router(user_router)
        server.include_router(item_router)

        # 添加启动/关闭处理器
        server.on_startup(initialize_db)
        server.on_shutdown(close_db)

        # 运行
        await server.serve()

        # 或获取应用以供外部使用
        app = server.app
    """

    def __init__(self, config: Optional[APIConfig] = None):
        if not FASTAPI_AVAILABLE:
            raise RuntimeError("FastAPI not installed. Install with: pip install pycore[api]")

        self.config = config or APIConfig()
        self._logger = get_logger()
        self._startup_handlers: list[Callable] = list(self.config.startup_handlers)
        self._shutdown_handlers: list[Callable] = list(self.config.shutdown_handlers)
        self._app: Optional[FastAPI] = None

    @property
    def app(self) -> FastAPI:
        """获取或创建 FastAPI 应用。"""
        if self._app is None:
            self._app = self._create_app()
        return self._app

    def _create_app(self) -> FastAPI:
        """使用配置创建 FastAPI 应用。"""

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # 启动
            self._logger.info("Starting API server...")
            for handler in self._startup_handlers:
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
            self._logger.info("API server started")

            yield

            # 关闭
            self._logger.info("Shutting down API server...")
            for handler in self._shutdown_handlers:
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
            self._logger.info("API server stopped")

        app = FastAPI(
            title=self.config.title,
            description=self.config.description,
            version=self.config.version,
            docs_url=self.config.docs_url if self.config.debug else None,
            redoc_url=self.config.redoc_url if self.config.debug else None,
            openapi_url=self.config.openapi_url if self.config.debug else None,
            lifespan=lifespan,
        )

        # 添加 CORS 中间件
        if self.config.cors_enabled:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=self.config.cors_origins,
                allow_credentials=True,
                allow_methods=self.config.cors_methods,
                allow_headers=self.config.cors_headers,
            )

        # 添加健康检查端点
        @app.get("/health")
        async def health_check():
            return {"status": "healthy", "version": self.config.version}

        return app

    def include_router(self, router, **kwargs):
        """在应用中包含路由。"""
        # 处理 APIRouter 包装器和 FastAPI 路由
        if hasattr(router, "router"):
            self.app.include_router(router.router, **kwargs)
        else:
            self.app.include_router(router, **kwargs)

    def on_startup(self, handler: Callable):
        """注册启动处理器。"""
        self._startup_handlers.append(handler)
        return handler

    def on_shutdown(self, handler: Callable):
        """注册关闭处理器。"""
        self._shutdown_handlers.append(handler)
        return handler

    def add_middleware(self, middleware_class, **options):
        """向应用添加中间件。"""
        self.app.add_middleware(middleware_class, **options)

    async def serve(self):
        """
        异步启动服务器。

        用法：
            await server.serve()
        """
        if not UVICORN_AVAILABLE:
            raise RuntimeError("uvicorn not installed. Install with: pip install uvicorn")

        config = uvicorn.Config(
            app=self.app,
            host=self.config.host,
            port=self.config.port,
            reload=self.config.reload,
            workers=self.config.workers,
            log_level="debug" if self.config.debug else "info",
        )
        server = uvicorn.Server(config)
        await server.serve()

    def run(self):
        """
        同步启动服务器。

        用法：
            server.run()
        """
        if not UVICORN_AVAILABLE:
            raise RuntimeError("uvicorn not installed. Install with: pip install uvicorn")

        uvicorn.run(
            self.app,
            host=self.config.host,
            port=self.config.port,
            reload=self.config.reload,
            workers=self.config.workers,
            log_level="debug" if self.config.debug else "info",
        )


def create_app(
    title: str = "PyCore API",
    version: str = "1.0.0",
    debug: bool = False,
    **kwargs,
) -> FastAPI:
    """
    应用工厂函数。

    使用标准配置创建 FastAPI 应用。

    用法：
        app = create_app(title="My API", debug=True)

        @app.get("/")
        async def root():
            return {"message": "Hello"}
    """
    config = APIConfig(
        title=title,
        version=version,
        debug=debug,
        **kwargs,
    )
    server = APIServer(config)
    return server.app


# 便捷导出
__all__ = [
    "APIConfig",
    "APIServer",
    "create_app",
]
