"""
OpenAI 兼容的 LLM 提供商。

支持 OpenAI、Azure OpenAI 和兼容的 API（DeepSeek、Ollama 等）。
"""

import asyncio
import json
from typing import Any, AsyncIterator, Optional

from pycore.core.exceptions import LLMError, TokenLimitError
from pycore.core.logger import get_logger
from pycore.integrations.llm.base import (
    LLMConfig,
    LLMProvider,
    LLMResponse,
    Message,
    ToolCall,
    ToolDefinition,
)

# 尝试导入 OpenAI
try:
    from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None

# 尝试导入 tenacity 用于重试
try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
    )

    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False


class OpenAIProvider(LLMProvider):
    """
    OpenAI 兼容的 LLM 提供商。

    支持：
    - OpenAI API
    - Azure OpenAI
    - DeepSeek（通过 base_url）
    - Ollama（通过 base_url）
    - 任何 OpenAI 兼容的 API

    用法：
        # OpenAI
        provider = OpenAIProvider(api_key="sk-...")
        response = await provider.chat([Message.user("Hello")])

        # DeepSeek
        provider = OpenAIProvider(
            api_key="your-key",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat"
        )

        # Azure OpenAI
        provider = OpenAIProvider(
            api_key="your-key",
            base_url="https://your-resource.openai.azure.com",
            api_version="2024-02-15-preview",
            model="gpt-4"
        )

        # Ollama
        provider = OpenAIProvider(
            base_url="http://localhost:11434/v1",
            model="llama2"
        )
    """

    def __init__(self, config: Optional[LLMConfig] = None, **kwargs):
        if not OPENAI_AVAILABLE:
            raise RuntimeError("openai not installed. Install with: pip install pycore[llm]")

        super().__init__(config, **kwargs)
        self._logger = get_logger()
        self._client: Optional[AsyncOpenAI] = None

    @property
    def client(self) -> AsyncOpenAI:
        """获取或创建 OpenAI 客户端。"""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                max_retries=0,  # 我们自己处理重试
            )
        return self._client

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        发送聊天完成请求。

        参数：
            messages: 消息列表
            tools: 可选的工具列表
            **kwargs: 额外选项（temperature、max_tokens 等）

        返回：
            LLM 响应

        抛出：
            LLMError: API 错误时
            TokenLimitError: 超出 token 限制时
        """
        # 构建请求参数
        params = self._build_params(messages, tools, **kwargs)

        # 使用重试逻辑执行
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self.client.chat.completions.create(**params)
                return self._parse_response(response)

            except Exception as e:
                error_type = type(e).__name__

                # 检查速率限制
                if "rate" in str(e).lower() or "429" in str(e):
                    if attempt < self.config.max_retries:
                        delay = self.config.retry_delay * (2**attempt)
                        self._logger.warning(
                            f"Rate limited, retrying in {delay}s...",
                            attempt=attempt + 1,
                        )
                        await asyncio.sleep(delay)
                        continue

                # 检查 token 限制
                if "token" in str(e).lower() and "limit" in str(e).lower():
                    raise TokenLimitError(
                        str(e),
                        model=self.config.model,
                    )

                # 检查超时
                if "timeout" in str(e).lower():
                    if attempt < self.config.max_retries:
                        self._logger.warning(
                            f"Timeout, retrying...",
                            attempt=attempt + 1,
                        )
                        await asyncio.sleep(self.config.retry_delay)
                        continue

                # 其他错误
                self._logger.error(f"LLM error: {error_type}: {e}")
                raise LLMError(
                    str(e),
                    provider="openai",
                    model=self.config.model,
                )

        raise LLMError(
            "Max retries exceeded",
            provider="openai",
            model=self.config.model,
        )

    async def chat_stream(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        流式传输聊天完成响应。

        生成：
            到达的响应 token

        用法：
            async for token in provider.chat_stream(messages):
                print(token, end="", flush=True)
        """
        params = self._build_params(messages, tools, stream=True, **kwargs)

        try:
            stream = await self.client.chat.completions.create(**params)

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            self._logger.error(f"Stream error: {e}")
            raise LLMError(
                str(e),
                provider="openai",
                model=self.config.model,
            )

    def _build_params(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
        **kwargs,
    ) -> dict[str, Any]:
        """构建 API 请求参数。"""
        # 将消息转换为字典格式
        message_dicts = [m.to_dict() for m in messages]

        # 基础参数
        params = {
            "model": kwargs.get("model", self.config.model),
            "messages": message_dicts,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "frequency_penalty": kwargs.get("frequency_penalty", self.config.frequency_penalty),
            "presence_penalty": kwargs.get("presence_penalty", self.config.presence_penalty),
        }

        # 可选参数
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if max_tokens:
            params["max_tokens"] = max_tokens

        # 工具
        if tools:
            params["tools"] = [t.to_dict() for t in tools]
            params["tool_choice"] = kwargs.get("tool_choice", "auto")

        # 流式传输
        if kwargs.get("stream"):
            params["stream"] = True

        # 额外的 kwargs
        for key in ["stop", "seed", "response_format", "logprobs"]:
            if key in kwargs:
                params[key] = kwargs[key]

        return params

    def _parse_response(self, response) -> LLMResponse:
        """解析 OpenAI API 响应。"""
        choice = response.choices[0]
        message = choice.message

        # 解析工具调用（如果存在）
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        type=tc.type,
                        function={
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    )
                )

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            model=response.model,
            finish_reason=choice.finish_reason or "stop",
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
            total_tokens=response.usage.total_tokens if response.usage else 0,
            raw=response.model_dump() if hasattr(response, "model_dump") else None,
        )

    async def close(self):
        """关闭客户端连接。"""
        if self._client:
            await self._client.close()
            self._client = None
