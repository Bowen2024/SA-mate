# PyCore Services 开发规范

## 服务层架构

PyCore 提供三层服务架构：

| 服务类型 | 状态机 | 卡死检测 | 暂停恢复 | 使用场景 |
|---------|--------|---------|---------|---------|
| `SimpleService` | 无 | 无 | 无 | CRUD、简单业务逻辑 |
| `BaseService` | 3 状态 | 无 | 无 | 需要生命周期管理 |
| `AgentService` | 7 状态 | 有 | 有 | AI Agent、对话服务 |

## SimpleService 使用

最轻量级的服务基类，适合简单的 CRUD 服务：

```python
from pycore.services import SimpleService

class UserService(SimpleService):
    name: str = "user_service"

    async def create_user(self, data: dict) -> dict:
        # 业务逻辑
        return {"id": 1, **data}

    async def get_user(self, user_id: int) -> dict:
        # 业务逻辑
        return {"id": user_id, "name": "Alice"}

# 使用
service = UserService()
user = await service.create_user({"name": "Alice"})
```

## BaseService 使用

带简化状态机（3 状态）的服务基类：

```python
from pycore.services import BaseService

class DataProcessor(BaseService):
    name: str = "processor"

    async def process(self, data):
        # 处理逻辑
        return processed_data

# 使用上下文管理器
service = DataProcessor()
async with service.running():
    result = await service.process(input_data)
# 自动回到 IDLE 状态
```

## AgentService 使用

AI Agent 专用服务，包含完整状态机和卡死检测：

```python
from pycore.services import AgentService

class ChatAgent(AgentService):
    name: str = "chat_agent"

    async def step(self) -> str:
        # 执行一步对话
        response = await llm.chat(self.context.get_messages())
        self.context.add_message("assistant", response)
        return response

    async def should_stop(self) -> bool:
        # 停止条件
        last_msg = self.context.messages[-1]
        return "goodbye" in last_msg.content.lower()

# 运行 Agent
agent = ChatAgent()
result = await agent.run("Hello!")
```

## 架构选择指南

| 应用类型 | 架构选择 | 说明 |
|---------|---------|------|
| 普通业务系统（无 AI 功能）| Router → Service → Repository | 不需要 Plugin 层 |
| AI Agent 应用（有对话/智能功能）| Router → Plugin → Service | Plugin 作为 LLM 可调用的工具 |

## Repository 基类

```python
# src/repositories/base.py
from typing import TypeVar, Generic, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

T = TypeVar("T")

class BaseRepository(Generic[T]):
    def __init__(self, db: AsyncSession, model: type[T]):
        self.db = db
        self.model = model

    async def get_by_id(self, id: int) -> Optional[T]:
        result = await self.db.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def create(self, obj: T) -> T:
        self.db.add(obj)
        await self.db.flush()
        return obj
```

## 数据库会话管理

```python
# src/db/session.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

engine = create_async_engine(DATABASE_URL, echo=DEBUG)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

## AgentContext 使用

AgentService 使用 AgentContext 管理对话上下文：

```python
# 添加消息
agent.context.add_message("user", "Hello")
agent.context.add_message("assistant", "Hi there!")

# 获取消息
messages = agent.context.get_messages()  # 全部
recent = agent.context.get_messages(n=5)  # 最近 5 条

# 获取 LLM 格式
dicts = agent.context.get_messages_as_dicts()

# 元数据
agent.context.set("key", "value")
value = agent.context.get("key")

# 清除
agent.context.clear_messages()  # 只清消息
agent.context.clear()           # 全部清除
```

## 向后兼容

为保持向后兼容，`ServiceContext` 是 `AgentContext` 的别名：

```python
from pycore.services import ServiceContext  # 等同于 AgentContext
```
