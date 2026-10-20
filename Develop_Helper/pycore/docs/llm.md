# LLM 集成

LLM 集成 (`pycore.integrations.llm`) 提供统一的大语言模型接口，支持 OpenAI、Azure OpenAI、DeepSeek、Ollama 等兼容 OpenAI API 的服务。

## 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [提供商配置](#提供商配置)
- [对话接口](#对话接口)
- [工具调用](#工具调用)
- [流式响应](#流式响应)
- [Token 计数](#token-计数)
- [完整示例](#完整示例)

---

## 安装

LLM 集成需要额外安装依赖：

```bash
pip install pycore[llm]
```

### 导入

```python
from pycore.integrations.llm import (
    # 核心类
    LLMProvider,
    LLMConfig,
    LLMResponse,
    Message,
    ToolCall,
    ToolDefinition,
    # 提供商
    OpenAIProvider,
    create_provider,
    # 工具
    TokenCounter,
    estimate_tokens,
)
```

---

## 快速开始

```python
import asyncio
from pycore.integrations.llm import OpenAIProvider, Message

async def main():
    # 创建提供商
    provider = OpenAIProvider(
        api_key="sk-...",
        model="gpt-4o-mini",
    )

    # 发送消息
    response = await provider.chat([
        Message.system("You are a helpful assistant."),
        Message.user("What is Python?"),
    ])

    print(response.content)
    print(f"Tokens used: {response.total_tokens}")

    await provider.close()

asyncio.run(main())
```

---

## 提供商配置

### OpenAI

```python
from pycore.integrations.llm import OpenAIProvider

provider = OpenAIProvider(
    api_key="sk-...",
    model="gpt-4o-mini",
    temperature=0.7,
    max_tokens=1000,
)
```

### DeepSeek

```python
provider = OpenAIProvider(
    api_key="your-deepseek-key",
    base_url="https://api.deepseek.com/v1",
    model="deepseek-chat",
)
```

### Azure OpenAI

```python
provider = OpenAIProvider(
    api_key="your-azure-key",
    base_url="https://your-resource.openai.azure.com",
    api_version="2024-02-15-preview",
    model="gpt-4",
)
```

### Ollama（本地）

```python
provider = OpenAIProvider(
    base_url="http://localhost:11434/v1",
    model="llama2",
    api_key="ollama",  # Ollama 不需要真实 key
)
```

### 使用工厂函数

```python
from pycore.integrations.llm import create_provider

# 自动选择提供商
provider = create_provider("openai", api_key="sk-...")
provider = create_provider("azure", api_key="...", base_url="...")
provider = create_provider("ollama", base_url="http://localhost:11434/v1")
```

### LLMConfig 完整配置

```python
from pycore.integrations.llm import LLMConfig, OpenAIProvider

config = LLMConfig(
    # 模型设置
    model="gpt-4o-mini",
    temperature=0.7,          # 0-2
    max_tokens=1000,          # 最大生成 token
    top_p=1.0,                # 0-1
    frequency_penalty=0,      # -2 to 2
    presence_penalty=0,       # -2 to 2

    # API 设置
    api_key="sk-...",
    base_url=None,            # 自定义 API 地址
    api_version=None,         # Azure API 版本
    timeout=60.0,             # 请求超时

    # 重试设置
    max_retries=3,
    retry_delay=1.0,
)

provider = OpenAIProvider(config=config)
```

---

## 对话接口

### Message 类

```python
from pycore.integrations.llm import Message

# 创建消息
msg = Message(role="user", content="Hello")

# 工厂方法
system_msg = Message.system("You are a helpful assistant.")
user_msg = Message.user("What is Python?")
assistant_msg = Message.assistant("Python is a programming language.")
tool_msg = Message.tool("Result: 42", tool_call_id="call_123")

# 转换为字典
data = msg.to_dict()
# {"role": "user", "content": "Hello"}
```

### chat() 方法

```python
# 基本对话
response = await provider.chat([
    Message.system("You are a helpful assistant."),
    Message.user("Hello!"),
])

print(response.content)        # 回复内容
print(response.model)          # 使用的模型
print(response.finish_reason)  # 结束原因
print(response.prompt_tokens)  # 提示 token
print(response.completion_tokens)  # 生成 token
print(response.total_tokens)   # 总 token
```

### 覆盖配置参数

```python
# 单次调用覆盖配置
response = await provider.chat(
    messages,
    temperature=0.9,
    max_tokens=500,
    model="gpt-4",  # 覆盖默认模型
)
```

### complete() 简单接口

```python
# 快速补全
answer = await provider.complete("Explain machine learning in one sentence.")
print(answer)
```

---

## 工具调用

### 定义工具

```python
from pycore.integrations.llm import ToolDefinition

# 定义工具
get_weather = ToolDefinition(
    name="get_weather",
    description="Get the current weather for a city",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name"
            },
            "units": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "default": "celsius"
            }
        },
        "required": ["city"]
    }
)

calculator = ToolDefinition(
    name="calculator",
    description="Perform basic math calculations",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Math expression to evaluate"
            }
        },
        "required": ["expression"]
    }
)

tools = [get_weather, calculator]
```

### 工具调用流程

```python
import json

# 带工具的对话
response = await provider.chat(
    messages=[Message.user("What's the weather in Paris?")],
    tools=tools,
)

# 检查是否有工具调用
if response.has_tool_calls:
    for tool_call in response.tool_calls:
        print(f"Tool: {tool_call.name}")
        print(f"Args: {tool_call.arguments}")

        # 解析参数
        args = json.loads(tool_call.arguments)

        # 执行工具
        if tool_call.name == "get_weather":
            result = get_weather_data(args["city"])
        elif tool_call.name == "calculator":
            result = eval(args["expression"])

        # 添加工具结果到消息
        messages.append(response.to_message())  # 助手的工具调用消息
        messages.append(Message.tool(
            content=str(result),
            tool_call_id=tool_call.id,
            name=tool_call.name,
        ))

    # 继续对话获取最终回答
    final_response = await provider.chat(messages, tools=tools)
    print(final_response.content)
else:
    # 直接得到回答
    print(response.content)
```

### 完整工具调用循环

```python
async def chat_with_tools(provider, messages, tools, max_iterations=10):
    """带工具调用的对话循环"""
    for _ in range(max_iterations):
        response = await provider.chat(messages, tools=tools)

        if not response.has_tool_calls:
            return response.content

        # 处理工具调用
        messages.append(response.to_message())

        for tool_call in response.tool_calls:
            result = await execute_tool(tool_call)
            messages.append(Message.tool(result, tool_call.id, tool_call.name))

    return "Max iterations reached"
```

---

## 流式响应

### 基本流式

```python
# 流式输出
async for token in provider.chat_stream(messages):
    print(token, end="", flush=True)

print()  # 换行
```

### 收集流式响应

```python
async def get_streamed_response(provider, messages):
    """收集完整的流式响应"""
    full_response = ""
    async for token in provider.chat_stream(messages):
        full_response += token
        print(token, end="", flush=True)
    print()
    return full_response
```

### 流式回调

```python
async def stream_with_callback(provider, messages, on_token):
    """带回调的流式响应"""
    async for token in provider.chat_stream(messages):
        await on_token(token)

# 使用
async def print_token(token):
    print(token, end="")

await stream_with_callback(provider, messages, print_token)
```

---

## Token 计数

### TokenCounter 类

```python
from pycore.integrations.llm import TokenCounter

# 创建计数器（自动选择编码）
counter = TokenCounter("gpt-4")

# 计数文本
count = counter.count_text("Hello, world!")
print(f"Tokens: {count}")

# 计数消息
messages = [
    Message.system("You are helpful."),
    Message.user("What is Python?"),
]
count = counter.count_messages(messages)
print(f"Total tokens: {count}")

# 截断文本
truncated = counter.truncate_text("Very long text...", max_tokens=100)
```

### 检查上下文限制

```python
# 检查是否超出上下文
if counter.fits_context(messages, context_limit=8192, completion_tokens=1000):
    response = await provider.chat(messages)
else:
    # 需要截断或压缩消息
    pass
```

### 快速估算

```python
from pycore.integrations.llm import estimate_tokens

# 不需要 tiktoken 的快速估算
count = estimate_tokens("Hello, world!")  # ~3

# 中文文本
count = estimate_tokens("你好世界")  # ~3
```

### 上下文限制参考

```python
from pycore.integrations.llm.token_counter import CONTEXT_LIMITS, get_context_limit

# 预定义限制
print(CONTEXT_LIMITS)
# {
#     "gpt-4": 8192,
#     "gpt-4-32k": 32768,
#     "gpt-4-turbo": 128000,
#     "gpt-4o": 128000,
#     "gpt-3.5-turbo": 4096,
#     "deepseek-chat": 32768,
#     ...
# }

# 获取模型限制
limit = get_context_limit("gpt-4o-mini")  # 128000
```

---

## 完整示例

```python
"""LLM 集成完整示例"""

import asyncio
import json
from pycore.core import Logger, LoggerConfig, LogLevel
from pycore.integrations.llm import (
    OpenAIProvider,
    Message,
    ToolDefinition,
    TokenCounter,
)

# 配置日志
logger = Logger.configure(LoggerConfig(level=LogLevel.DEBUG))

# 定义工具
tools = [
    ToolDefinition(
        name="get_weather",
        description="Get weather for a city",
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"]
        }
    ),
    ToolDefinition(
        name="calculate",
        description="Calculate a math expression",
        parameters={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Math expression"}
            },
            "required": ["expression"]
        }
    ),
]

# 工具实现
def execute_tool(tool_call):
    args = json.loads(tool_call.arguments)

    if tool_call.name == "get_weather":
        city = args["city"]
        # 模拟天气数据
        return f"Weather in {city}: 22°C, sunny"

    elif tool_call.name == "calculate":
        try:
            result = eval(args["expression"])
            return f"Result: {result}"
        except:
            return "Error: Invalid expression"

    return "Unknown tool"

async def main():
    # 创建提供商
    provider = OpenAIProvider(
        api_key="your-api-key",
        model="gpt-4o-mini",
        temperature=0.7,
    )

    # Token 计数器
    counter = TokenCounter("gpt-4o-mini")

    # 初始消息
    messages = [
        Message.system("You are a helpful assistant with access to weather and calculator tools."),
        Message.user("What's the weather in Tokyo? Also, calculate 15 * 24."),
    ]

    # 检查 token
    token_count = counter.count_messages(messages)
    logger.info(f"Initial tokens: {token_count}")

    # 对话循环
    for iteration in range(5):
        logger.info(f"Iteration {iteration + 1}")

        response = await provider.chat(messages, tools=tools)
        logger.debug(f"Tokens used: {response.total_tokens}")

        if response.has_tool_calls:
            logger.info(f"Tool calls: {len(response.tool_calls)}")

            # 添加助手消息
            messages.append(response.to_message())

            # 执行工具
            for tool_call in response.tool_calls:
                logger.debug(f"Executing: {tool_call.name}")
                result = execute_tool(tool_call)
                messages.append(Message.tool(result, tool_call.id, tool_call.name))

        else:
            # 最终回答
            logger.info("Got final answer")
            print("\n" + "=" * 50)
            print("RESPONSE:")
            print("=" * 50)
            print(response.content)
            print("=" * 50)
            break

    await provider.close()

if __name__ == "__main__":
    asyncio.run(main())
```

输出示例：
```
2024-01-01 12:00:00 | INFO  | Initial tokens: 45
2024-01-01 12:00:00 | INFO  | Iteration 1
2024-01-01 12:00:00 | DEBUG | Tokens used: 120
2024-01-01 12:00:00 | INFO  | Tool calls: 2
2024-01-01 12:00:00 | DEBUG | Executing: get_weather
2024-01-01 12:00:00 | DEBUG | Executing: calculate
2024-01-01 12:00:00 | INFO  | Iteration 2
2024-01-01 12:00:00 | DEBUG | Tokens used: 180
2024-01-01 12:00:00 | INFO  | Got final answer

==================================================
RESPONSE:
==================================================
The weather in Tokyo is 22°C and sunny. Also, 15 × 24 = 360.
==================================================
```
