"""
LLM 提供商的基础类和接口。

定义 LLM 提供商的抽象接口。
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, AsyncIterator, Optional, Union

from pydantic import BaseModel, Field

from pycore.core.exceptions import LLMError


class MessageRole(str, Enum):
    """消息角色枚举。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """
    LLM 消息模型。

    用法：
        msg = Message(role="user", content="Hello!")
        msg = Message.user("Hello!")
        msg = Message.system("You are a helpful assistant.")
    """

    role: str = Field(..., description="消息角色")
    content: Optional[str] = Field(None, description="消息内容")
    name: Optional[str] = Field(None, description="工具/函数名称")
    tool_call_id: Optional[str] = Field(None, description="工具响应的工具调用 ID")
    tool_calls: Optional[list["ToolCall"]] = Field(None, description="来自助手的工具调用")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典以供 API 调用。"""
        d = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.name:
            d["name"] = self.name
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            d["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        return d

    @classmethod
    def system(cls, content: str) -> "Message":
        """创建系统消息。"""
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> "Message":
        """创建用户消息。"""
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str, tool_calls: list["ToolCall"] = None) -> "Message":
        """创建助手消息。"""
        return cls(role="assistant", content=content, tool_calls=tool_calls)

    @classmethod
    def tool(cls, content: str, tool_call_id: str, name: str = None) -> "Message":
        """创建工具响应消息。"""
        return cls(role="tool", content=content, tool_call_id=tool_call_id, name=name)


class ToolCall(BaseModel):
    """来自 LLM 响应的工具调用。"""

    id: str = Field(..., description="工具调用 ID")
    type: str = Field(default="function", description="工具类型")
    function: dict[str, Any] = Field(..., description="函数名称和参数")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "function": self.function,
        }

    @property
    def name(self) -> str:
        """获取函数名称。"""
        return self.function.get("name", "")

    @property
    def arguments(self) -> str:
        """获取函数参数（JSON 字符串）。"""
        return self.function.get("arguments", "{}")


class ToolDefinition(BaseModel):
    """
    LLM 的工具定义。

    用法：
        tool = ToolDefinition(
            name="get_weather",
            description="Get weather for a city",
            parameters={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"}
                },
                "required": ["city"]
            }
        )
    """

    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}},
        description="参数的 JSON Schema",
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为 OpenAI 函数格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class LLMResponse(BaseModel):
    """
    LLM 响应模型。

    用法：
        if response.has_tool_calls:
            for tool_call in response.tool_calls:
                result = execute_tool(tool_call)
        else:
            print(response.content)
    """

    content: Optional[str] = Field(None, description="响应内容")
    tool_calls: list[ToolCall] = Field(default_factory=list, description="工具调用")
    model: str = Field(default="", description="使用的模型")
    finish_reason: str = Field(default="stop", description="完成原因")

    # 使用统计
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)

    # 原始响应
    raw: Optional[dict] = Field(None, description="原始 API 响应")

    @property
    def has_tool_calls(self) -> bool:
        """检查响应是否有工具调用。"""
        return len(self.tool_calls) > 0

    def to_message(self) -> Message:
        """将响应转换为助手消息。"""
        return Message.assistant(
            content=self.content,
            tool_calls=self.tool_calls if self.tool_calls else None,
        )


class LLMConfig(BaseModel):
    """
    LLM 提供商配置。

    用法：
        config = LLMConfig(
            model="gpt-4",
            temperature=0.7,
            max_tokens=1000
        )
    """

    # 模型设置
    model: str = Field(default="gpt-4o-mini", description="模型名称")
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(None, description="最大响应 token 数")
    top_p: float = Field(default=1.0, ge=0, le=1)
    frequency_penalty: float = Field(default=0, ge=-2, le=2)
    presence_penalty: float = Field(default=0, ge=-2, le=2)

    # API 设置
    api_key: Optional[str] = Field(None, description="API 密钥")
    base_url: Optional[str] = Field(None, description="API 的基础 URL")
    api_version: Optional[str] = Field(None, description="API 版本（用于 Azure）")
    timeout: float = Field(default=60.0, description="请求超时时间（秒）")

    # 重试设置
    max_retries: int = Field(default=3, description="最大重试次数")
    retry_delay: float = Field(default=1.0, description="重试之间的延迟")

    class Config:
        extra = "allow"  # Allow provider-specific settings


class LLMProvider(ABC):
    """
    LLM 提供商的抽象基础类。

    子类必须实现：
    - chat(): 发送消息并获取响应
    - chat_stream(): 流式传输响应 token

    用法：
        class MyProvider(LLMProvider):
            async def chat(self, messages, **kwargs):
                # 实现
                return LLMResponse(content="Hello!")

        provider = MyProvider(config)
        response = await provider.chat([Message.user("Hi")])
    """

    def __init__(self, config: Optional[LLMConfig] = None, **kwargs):
        """使用配置初始化提供商。"""
        if config:
            self.config = config
        else:
            self.config = LLMConfig(**kwargs)

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        发送消息并获取响应。

        参数：
            messages: 消息列表
            tools: 可选的工具列表
            **kwargs: 额外的提供商特定选项

        返回：
            LLM 响应
        """

    async def chat_stream(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        流式传输响应 token。

        默认实现回退到非流式传输。
        重写以实现真正的流式传输支持。

        生成：
            响应 token
        """
        response = await self.chat(messages, tools, **kwargs)
        if response.content:
            yield response.content

    async def complete(self, prompt: str, **kwargs) -> str:
        """
        简单的完成接口。

        参数：
            prompt: 用户提示

        返回：
            响应文本
        """
        response = await self.chat([Message.user(prompt)], **kwargs)
        return response.content or ""

    def count_tokens(self, messages: list[Message]) -> int:
        """
        计算消息中的 token 数。

        重写以使用特定分词器进行准确计数。
        """
        # 简单估算：约 4 个字符 per token
        total_chars = sum(len(m.content or "") for m in messages)
        return total_chars // 4
