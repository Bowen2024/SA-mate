"""
使用 contextvars 的执行上下文，用于请求作用域数据。

提供跨函数调用的异步安全上下文管理。
"""

from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from typing import Any, Optional

# 用于执行作用域数据的上下文变量
_execution_context: ContextVar[dict[str, Any]] = ContextVar(
    "execution_context",
    default={},
)


class ExecutionContext:
    """
    使用 contextvars 的请求作用域执行上下文。

    线程安全和异步安全的上下文，用于在函数调用间传递数据，
    无需显式参数传递。

    用法：
        # 设置上下文
        async with ExecutionContext.scope(request_id="123", user_id=456):
            # 在调用栈的任何地方访问上下文
            ctx = ExecutionContext.current()
            print(ctx.get("request_id"))  # "123"

            # 修改上下文
            ExecutionContext.set("processed", True)

        # 同步版本
        with ExecutionContext.sync_scope(key="value"):
            data = ExecutionContext.get("key")
    """

    @classmethod
    def current(cls) -> dict[str, Any]:
        """获取当前上下文字典。"""
        return _execution_context.get().copy()

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        """在当前上下文中设置值。"""
        ctx = _execution_context.get().copy()
        ctx[key] = value
        _execution_context.set(ctx)

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """从当前上下文获取值。"""
        return _execution_context.get().get(key, default)

    @classmethod
    def update(cls, **kwargs) -> None:
        """更新上下文中的多个值。"""
        ctx = _execution_context.get().copy()
        ctx.update(kwargs)
        _execution_context.set(ctx)

    @classmethod
    def delete(cls, key: str) -> None:
        """从上下文中移除键。"""
        ctx = _execution_context.get().copy()
        ctx.pop(key, None)
        _execution_context.set(ctx)

    @classmethod
    def clear(cls) -> None:
        """清除所有上下文数据。"""
        _execution_context.set({})

    @classmethod
    def has(cls, key: str) -> bool:
        """检查键是否存在于上下文中。"""
        return key in _execution_context.get()

    @classmethod
    @asynccontextmanager
    async def scope(cls, **kwargs):
        """
        创建新的异步上下文作用域。

        退出作用域时自动恢复上下文。

        用法：
            async with ExecutionContext.scope(request_id="123"):
                # request_id 在此处可用
                await process_request()
            # request_id 不再可用
        """
        # 保存当前上下文并设置新的
        token = _execution_context.set(kwargs)
        try:
            yield
        finally:
            # 恢复之前的上下文
            _execution_context.reset(token)

    @classmethod
    @contextmanager
    def sync_scope(cls, **kwargs):
        """
        创建新的同步上下文作用域。

        用法：
            with ExecutionContext.sync_scope(key="value"):
                data = ExecutionContext.get("key")
        """
        token = _execution_context.set(kwargs)
        try:
            yield
        finally:
            _execution_context.reset(token)

    @classmethod
    @asynccontextmanager
    async def nested_scope(cls, **kwargs):
        """
        创建继承自父级的作用域。

        用法：
            async with ExecutionContext.scope(a=1):
                async with ExecutionContext.nested_scope(b=2):
                    # a 和 b 都可用
                    print(ExecutionContext.get("a"))  # 1
                    print(ExecutionContext.get("b"))  # 2
        """
        current = _execution_context.get().copy()
        current.update(kwargs)
        token = _execution_context.set(current)
        try:
            yield
        finally:
            _execution_context.reset(token)


# 便捷函数
def execution_context() -> dict[str, Any]:
    """获取当前执行上下文。"""
    return ExecutionContext.current()
