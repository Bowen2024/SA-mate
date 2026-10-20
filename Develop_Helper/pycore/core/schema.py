"""
PyCore 的基础模式和数据模型。

提供框架中使用的通用 Pydantic 模型。
"""

from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    """
    操作的通用结果容器。

    提供标准化的方式返回成功/失败及数据。

    用法：
        # 成功
        result = Result(success=True, data={"key": "value"})

        # 失败
        result = Result(success=False, error="Something went wrong")

        # 检查结果
        if result:
            print(result.data)
        else:
            print(result.error)
    """

    success: bool = True
    data: Optional[T] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True

    def __bool__(self) -> bool:
        """允许在布尔上下文中使用 Result。"""
        return self.success

    def __str__(self) -> str:
        if self.success:
            return f"Result(success=True, data={self.data})"
        return f"Result(success=False, error={self.error})"

    @classmethod
    def ok(cls, data: T, **metadata) -> "Result[T]":
        """创建成功结果。"""
        return cls(success=True, data=data, metadata=metadata)

    @classmethod
    def fail(cls, error: str, **metadata) -> "Result[T]":
        """创建失败结果。"""
        return cls(success=False, error=error, metadata=metadata)

    def map(self, func) -> "Result":
        """如果成功则转换数据。"""
        if self.success and self.data is not None:
            return Result.ok(func(self.data), **self.metadata)
        return self

    def unwrap(self) -> T:
        """获取数据或抛出错误。"""
        if not self.success:
            raise ValueError(self.error or "Result is not successful")
        return self.data  # type: ignore

    def unwrap_or(self, default: T) -> T:
        """获取数据或返回默认值。"""
        if self.success and self.data is not None:
            return self.data
        return default


class Message(BaseModel):
    """
    用于通信的通用消息容器。

    用于服务、插件和执行上下文。
    """

    role: str = Field(..., description="消息角色（例如 system, user, assistant）")
    content: Optional[str] = Field(None, description="消息内容")
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"  # 允许额外字段

    @classmethod
    def system(cls, content: str, **kwargs) -> "Message":
        """创建系统消息。"""
        return cls(role="system", content=content, metadata=kwargs)

    @classmethod
    def user(cls, content: str, **kwargs) -> "Message":
        """创建用户消息。"""
        return cls(role="user", content=content, metadata=kwargs)

    @classmethod
    def assistant(cls, content: str, **kwargs) -> "Message":
        """创建助手消息。"""
        return cls(role="assistant", content=content, metadata=kwargs)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典，排除 None 值。"""
        result = {"role": self.role}
        if self.content is not None:
            result["content"] = self.content
        if self.metadata:
            result.update(self.metadata)
        return result


class Metadata(BaseModel):
    """
    可扩展的元数据容器。

    用于为任何实体添加元数据的基础类。
    """

    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    def add_tag(self, tag: str) -> "Metadata":
        """添加标签。"""
        if tag not in self.tags:
            self.tags.append(tag)
        return self

    def set(self, key: str, value: Any) -> "Metadata":
        """设置额外字段。"""
        self.extra[key] = value
        return self

    def get(self, key: str, default: Any = None) -> Any:
        """获取额外字段。"""
        return self.extra.get(key, default)


class Identifiable(BaseModel):
    """
    具有标识的实体的基础模型。
    """

    id: Optional[str] = None
    name: str
    description: Optional[str] = None

    def __hash__(self) -> int:
        return hash(self.id or self.name)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Identifiable):
            return (self.id or self.name) == (other.id or other.name)
        return False
