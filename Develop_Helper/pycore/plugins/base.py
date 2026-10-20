"""
PyCore 插件的基础类。

插件是可扩展功能的构建块。
它们结合了 Pydantic 验证和抽象异步执行。
"""

import json
from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field

from pycore.core.exceptions import PluginError


class PluginResult(BaseModel):
    """
    插件执行的标准结果。

    用法：
        # 成功
        result = PluginResult.ok("Task completed")

        # 带结构化数据
        result = PluginResult.ok({"key": "value"})

        # 错误
        result = PluginResult.fail("Something went wrong")

        # 检查结果
        if result:
            print(result.data)
    """

    success: bool = Field(default=True, description="是否成功")
    data: Any = Field(default=None, description="插件输出数据")
    error: Optional[str] = Field(default=None, description="失败时的错误消息")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="额外元数据"
    )

    class Config:
        arbitrary_types_allowed = True

    def __bool__(self) -> bool:
        """基于 success 字段判断结果。"""
        return self.success

    @property
    def output(self) -> Any:
        """向后兼容：output -> data"""
        return self.data

    def __str__(self) -> str:
        if self.error:
            return f"PluginResult(error={self.error})"
        if isinstance(self.data, str):
            return self.data
        return json.dumps(self.data, indent=2, default=str)

    def __add__(self, other: "PluginResult") -> "PluginResult":
        """合并两个结果。"""
        if self.error and other.error:
            return PluginResult(success=False, error=f"{self.error}; {other.error}")
        if self.error:
            return self
        if other.error:
            return other

        # 合并输出
        if isinstance(self.data, str) and isinstance(other.data, str):
            combined = f"{self.data}\n{other.data}"
        elif isinstance(self.data, dict) and isinstance(other.data, dict):
            combined = {**self.data, **other.data}
        elif isinstance(self.data, list) and isinstance(other.data, list):
            combined = self.data + other.data
        else:
            combined = [self.data, other.data]

        return PluginResult(
            success=True,
            data=combined,
            metadata={**self.metadata, **other.metadata},
        )

    @classmethod
    def ok(cls, data: Any, **metadata) -> "PluginResult":
        """创建成功结果。"""
        return cls(success=True, data=data, metadata=metadata)

    @classmethod
    def success(cls, data: Any, **metadata) -> "PluginResult":
        """创建成功结果。向后兼容 ok() 的别名。"""
        return cls.ok(data, **metadata)

    @classmethod
    def fail(cls, error: str, **metadata) -> "PluginResult":
        """创建失败结果。"""
        return cls(success=False, error=error, metadata=metadata)


class BasePlugin(ABC, BaseModel):
    """
    所有插件的抽象基础类。

    结合了 Pydantic 验证和抽象异步接口。

    用法：
        class MyPlugin(BasePlugin):
            name: str = "my_plugin"
            description: str = "Does something useful"

            async def execute(self, **kwargs) -> PluginResult:
                # 插件逻辑
                return self.ok("Done!")

        # 使用插件
        plugin = MyPlugin()
        result = await plugin(arg1="value")
    """

    name: str = Field(..., description="唯一插件名称")
    description: str = Field(..., description="插件描述")
    version: str = Field(default="1.0.0", description="插件版本")
    enabled: bool = Field(default=True, description="插件是否启用")
    parameters: Optional[dict[str, Any]] = Field(
        default=None, description="插件的参数模式"
    )

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"  # 允许子类添加字段

    async def __call__(self, **kwargs) -> PluginResult:
        """执行插件。"""
        if not self.enabled:
            return PluginResult.fail(f"Plugin '{self.name}' is disabled")
        try:
            return await self.execute(**kwargs)
        except Exception as e:
            return PluginResult.fail(f"Plugin '{self.name}' failed: {e}")

    @abstractmethod
    async def execute(self, **kwargs) -> PluginResult:
        """
        执行插件逻辑。必须由子类实现。

        返回：
            包含输出或错误的 PluginResult
        """

    def to_spec(self) -> dict[str, Any]:
        """
        将插件转换为规范字典。

        兼容 OpenAI 函数调用格式。
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
                or {"type": "object", "properties": {}, "required": []},
            },
        }

    async def setup(self) -> None:
        """
        可选的设置钩子，在首次执行前调用。

        重写以初始化资源。
        """
        pass

    async def teardown(self) -> None:
        """
        可选的清理钩子。

        重写以释放资源。
        """
        pass

    def ok(self, data: Any, **metadata) -> PluginResult:
        """创建成功结果的便捷方法。"""
        return PluginResult.ok(data, **metadata)

    def success(self, data: Any, **metadata) -> PluginResult:
        """创建成功结果的便捷方法。向后兼容 ok() 的别名。"""
        return self.ok(data, **metadata)

    def fail(self, error: str, **metadata) -> PluginResult:
        """创建失败结果的便捷方法。"""
        return PluginResult.fail(error, **metadata)
