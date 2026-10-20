"""
API module for PyCore.

Provides FastAPI integration with standardized patterns.
"""

from pycore.api.server import (
    APIServer,
    APIConfig,
    create_app,
)
from pycore.api.routes import (
    APIRouter,
    route,
    get,
    post,
    put,
    delete,
)
from pycore.api.middleware import (
    RequestContextMiddleware,
    ErrorHandlerMiddleware,
)
from pycore.api.responses import (
    APIResponse,
    success_response,
    error_response,
    paginated_response,
)

__all__ = [
    # Server
    "APIServer",
    "APIConfig",
    "create_app",
    # Routes
    "APIRouter",
    "route",
    "get",
    "post",
    "put",
    "delete",
    # Middleware
    "RequestContextMiddleware",
    "ErrorHandlerMiddleware",
    # Responses
    "APIResponse",
    "success_response",
    "error_response",
    "paginated_response",
]
