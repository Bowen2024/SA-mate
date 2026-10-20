"""
LLM 提供商的 token 计数工具。

提供估算功能，当 tiktoken 可用时提供准确计数。
"""

from typing import Optional, Union

from pycore.integrations.llm.base import Message

# 尝试导入 tiktoken
try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


class TokenCounter:
    """
    支持 tiktoken 的 token 计数器。

    当 tiktoken 不可用时回退到估算。

    用法：
        counter = TokenCounter("gpt-4")
        count = counter.count_messages(messages)
        count = counter.count_text("Hello world")
    """

    # 模型到编码的映射
    MODEL_ENCODINGS = {
        # GPT-4 模型
        "gpt-4": "cl100k_base",
        "gpt-4-32k": "cl100k_base",
        "gpt-4-turbo": "cl100k_base",
        "gpt-4o": "o200k_base",
        "gpt-4o-mini": "o200k_base",
        # GPT-3.5 模型
        "gpt-3.5-turbo": "cl100k_base",
        "gpt-3.5-turbo-16k": "cl100k_base",
        # 嵌入模型
        "text-embedding-ada-002": "cl100k_base",
        "text-embedding-3-small": "cl100k_base",
        "text-embedding-3-large": "cl100k_base",
    }

    # 聊天模型每条消息的 token 开销
    TOKENS_PER_MESSAGE = {
        "gpt-4": 3,
        "gpt-4o": 3,
        "gpt-4o-mini": 3,
        "gpt-3.5-turbo": 4,
    }

    def __init__(self, model: str = "gpt-4"):
        self.model = model
        self._encoding = None

        if TIKTOKEN_AVAILABLE:
            self._init_encoding()

    def _init_encoding(self):
        """初始化 tiktoken 编码。"""
        # 尝试精确模型匹配
        encoding_name = self.MODEL_ENCODINGS.get(self.model)

        # 尝试前缀匹配
        if not encoding_name:
            for prefix, enc in self.MODEL_ENCODINGS.items():
                if self.model.startswith(prefix):
                    encoding_name = enc
                    break

        # 默认为 cl100k_base
        if not encoding_name:
            encoding_name = "cl100k_base"

        try:
            self._encoding = tiktoken.get_encoding(encoding_name)
        except Exception:
            self._encoding = tiktoken.get_encoding("cl100k_base")

    def count_text(self, text: str) -> int:
        """
        计算文本中的 token 数。

        参数：
            text: 输入文本

        返回：
            Token 数量
        """
        if not text:
            return 0

        if self._encoding:
            return len(self._encoding.encode(text))

        # 回退估算：英文约 4 个字符 per token
        return len(text) // 4

    def count_message(self, message: Message) -> int:
        """
        计算单个消息中的 token 数。

        参数：
            message: 要计算的消息

        返回：
            包括开销的 token 数量
        """
        tokens = 0

        # 消息开销
        tokens_per_message = 3  # 默认
        for prefix, overhead in self.TOKENS_PER_MESSAGE.items():
            if self.model.startswith(prefix):
                tokens_per_message = overhead
                break

        tokens += tokens_per_message

        # 角色
        tokens += self.count_text(message.role)

        # 内容
        if message.content:
            tokens += self.count_text(message.content)

        # 名称
        if message.name:
            tokens += self.count_text(message.name)
            tokens += 1  # 名称开销

        return tokens

    def count_messages(self, messages: list[Message]) -> int:
        """
        计算消息列表中的总 token 数。

        参数：
            messages: 消息列表

        返回：
            总 token 数量
        """
        total = sum(self.count_message(m) for m in messages)
        total += 3  # 回复启动 token
        return total

    def truncate_text(self, text: str, max_tokens: int) -> str:
        """
        截断文本以适合 token 限制。

        参数：
            text: 输入文本
            max_tokens: 最大 token 数

        返回：
            截断后的文本
        """
        if self.count_text(text) <= max_tokens:
            return text

        if self._encoding:
            tokens = self._encoding.encode(text)
            if len(tokens) <= max_tokens:
                return text
            return self._encoding.decode(tokens[:max_tokens])

        # 回退：估算字符数
        estimated_chars = max_tokens * 4
        return text[:estimated_chars]

    def fits_context(
        self,
        messages: list[Message],
        context_limit: int,
        completion_tokens: int = 1000,
    ) -> bool:
        """
        检查消息是否适合上下文窗口。

        参数：
            messages: 要检查的消息
            context_limit: 模型的上下文限制
            completion_tokens: 为完成保留的 token

        返回：
            如果消息适合则返回 True
        """
        used_tokens = self.count_messages(messages)
        return used_tokens + completion_tokens <= context_limit


def estimate_tokens(text: str) -> int:
    """
    快速 token 估算，无需模型特定计数。

    使用简单启发式：英文文本约 4 个字符 per token。

    参数：
        text: 输入文本

    返回：
        估算的 token 数量
    """
    if not text:
        return 0

    # 针对不同字符类型调整
    # ASCII 约 4 个字符 per token
    # 中文/日文约 1-2 个字符 per token
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    non_ascii_chars = len(text) - ascii_chars

    ascii_tokens = ascii_chars / 4
    non_ascii_tokens = non_ascii_chars / 1.5  # CJK 字符使用更多 token

    return int(ascii_tokens + non_ascii_tokens)


# 模型上下文限制
CONTEXT_LIMITS = {
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "gpt-4-turbo": 128000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-3.5-turbo": 4096,
    "gpt-3.5-turbo-16k": 16384,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "deepseek-chat": 32768,
    "deepseek-coder": 16384,
}


def get_context_limit(model: str) -> int:
    """
    获取模型的上下文限制。

    参数：
        model: 模型名称

    返回：
        上下文限制（token 数，默认 8192）
    """
    # 精确匹配
    if model in CONTEXT_LIMITS:
        return CONTEXT_LIMITS[model]

    # 前缀匹配
    for prefix, limit in CONTEXT_LIMITS.items():
        if model.startswith(prefix):
            return limit

    return 8192  # 安全默认值
