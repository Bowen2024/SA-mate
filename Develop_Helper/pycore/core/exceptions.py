"""
PyCore 异常层次结构。

所有框架异常都继承自 PyCoreError，便于捕获。
"""

from typing import Any, Optional


class PyCoreError(Exception):
    """所有 PyCore 错误的基础异常。"""

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"[{self.code}] {self.message} - {self.details}"
        return f"[{self.code}] {self.message}"

    def to_dict(self) -> dict[str, Any]:
        """将异常转换为字典以便序列化。"""
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


class ConfigurationError(PyCoreError):
    """配置加载或验证失败时抛出。"""

    def __init__(
        self,
        message: str,
        *,
        config_path: Optional[str] = None,
        field: Optional[str] = None,
    ):
        details = {}
        if config_path:
            details["config_path"] = config_path
        if field:
            details["field"] = field
        super().__init__(message, code="CONFIG_ERROR", details=details)


class ValidationError(PyCoreError):
    """数据验证失败时抛出。"""

    def __init__(
        self,
        message: str,
        *,
        field: Optional[str] = None,
        value: Optional[Any] = None,
    ):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)
        super().__init__(message, code="VALIDATION_ERROR", details=details)


class PluginError(PyCoreError):
    """插件操作失败时抛出。"""

    def __init__(
        self,
        message: str,
        *,
        plugin_name: Optional[str] = None,
        operation: Optional[str] = None,
    ):
        details = {}
        if plugin_name:
            details["plugin"] = plugin_name
        if operation:
            details["operation"] = operation
        super().__init__(message, code="PLUGIN_ERROR", details=details)


class PluginNotFoundError(PluginError):
    """请求的插件未找到时抛出。"""

    def __init__(self, plugin_name: str):
        super().__init__(
            f"Plugin '{plugin_name}' not found",
            plugin_name=plugin_name,
            operation="lookup",
        )
        self.code = "PLUGIN_NOT_FOUND"


class ServiceError(PyCoreError):
    """服务操作失败时抛出。"""

    def __init__(
        self,
        message: str,
        *,
        service_name: Optional[str] = None,
        state: Optional[str] = None,
    ):
        details = {}
        if service_name:
            details["service"] = service_name
        if state:
            details["state"] = state
        super().__init__(message, code="SERVICE_ERROR", details=details)


class ServiceStateError(ServiceError):
    """服务状态转换无效时抛出。"""

    def __init__(
        self,
        message: str,
        *,
        service_name: Optional[str] = None,
        from_state: Optional[str] = None,
        to_state: Optional[str] = None,
    ):
        details = {}
        if from_state:
            details["from_state"] = from_state
        if to_state:
            details["to_state"] = to_state
        super().__init__(message, service_name=service_name)
        self.details.update(details)
        self.code = "STATE_TRANSITION_ERROR"


class ExecutionError(PyCoreError):
    """执行/流程操作失败时抛出。"""

    def __init__(
        self,
        message: str,
        *,
        flow_name: Optional[str] = None,
        step: Optional[str] = None,
    ):
        details = {}
        if flow_name:
            details["flow"] = flow_name
        if step:
            details["step"] = step
        super().__init__(message, code="EXECUTION_ERROR", details=details)


class TimeoutError(ExecutionError):
    """操作超时时抛出。"""

    def __init__(
        self,
        message: str,
        *,
        timeout_seconds: Optional[float] = None,
        operation: Optional[str] = None,
    ):
        details = {}
        if timeout_seconds:
            details["timeout_seconds"] = timeout_seconds
        if operation:
            details["operation"] = operation
        super().__init__(message)
        self.details.update(details)
        self.code = "TIMEOUT_ERROR"


class RetryExhaustedError(ExecutionError):
    """所有重试尝试都耗尽时抛出。"""

    def __init__(
        self,
        message: str,
        *,
        attempts: Optional[int] = None,
        last_error: Optional[Exception] = None,
    ):
        details = {}
        if attempts:
            details["attempts"] = attempts
        if last_error:
            details["last_error"] = str(last_error)
        super().__init__(message)
        self.details.update(details)
        self.code = "RETRY_EXHAUSTED"
        self.last_error = last_error


class IntegrationError(PyCoreError):
    """外部集成失败时抛出。"""

    def __init__(
        self,
        message: str,
        *,
        integration: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        details = {}
        if integration:
            details["integration"] = integration
        if provider:
            details["provider"] = provider
        super().__init__(message, code="INTEGRATION_ERROR", details=details)


class LLMError(IntegrationError):
    """LLM 操作失败时抛出。"""

    def __init__(
        self,
        message: str,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ):
        super().__init__(message, integration="llm", provider=provider)
        if model:
            self.details["model"] = model
        self.code = "LLM_ERROR"


class TokenLimitError(LLMError):
    """超出 token 限制时抛出。"""

    def __init__(
        self,
        message: str,
        *,
        current_tokens: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ):
        super().__init__(message)
        if current_tokens:
            self.details["current_tokens"] = current_tokens
        if max_tokens:
            self.details["max_tokens"] = max_tokens
        self.code = "TOKEN_LIMIT_EXCEEDED"
