# PyCore API 开发规范

## FastAPI 路由参数装饰器使用规则

`Field()` 仅用于 Pydantic 模型，路由参数使用对应装饰器：

```python
from fastapi import Query, Path, Header, Depends

@router.get("/items/{item_id}")
async def get_item(
    item_id: str,                              # 路径参数（自动识别）
    page: int = Query(1, ge=1),                # 查询参数
    token: str = Header(...),                  # 请求头
    user: User = Depends(get_current_user),    # 依赖注入
):
    ...
```

## 参数来源对照表

| 参数来源 | 装饰器 | 示例 |
|---------|--------|------|
| URL 路径 | 自动/`Path()` | `/users/{user_id}` |
| 查询字符串 | `Query()` | `?page=1&size=10` |
| 请求头 | `Header()` | `Authorization: Bearer xxx` |
| Cookie | `Cookie()` | `session_id=abc` |
| 请求体 | Pydantic Model | `class CreateRequest(BaseModel)` |
| 依赖注入 | `Depends()` | `Depends(get_db)` |

## 用户身份获取规范

用户身份**必须通过 JWT Token 解析**，从 `Depends(get_current_user)` 获取：

```python
@router.post("/create")
async def create(
    request: CreateRequest,
    current_user: User = Depends(get_current_user),  # 从 token 解析
):
    user_id = current_user.id
    ...
```

## 请求体与模型定义

```python
# Pydantic 模型中使用 Field()
class CreateTaskRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)

# 路由中使用模型接收请求体
@router.post("/tasks")
async def create_task(request: CreateTaskRequest):  # 自动解析为请求体
    ...
```

## 依赖注入规范

使用 `Depends()` 注入数据库会话、插件注册表等依赖：

```python
from fastapi import Depends

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session

@router.post("/items")
async def create_item(
    data: ItemCreate,
    db: AsyncSession = Depends(get_db),
    plugins: PluginRegistry = Depends(get_plugins),
):
    ...
```

## 认证模式标准实现

```python
# src/api/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """从 JWT Token 解析当前用户"""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="无效凭据")
        # 从数据库获取用户
        return await user_repo.get_by_id(user_id)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效 Token")
```

## 错误处理规范（路由层）

```python
from pycore.api import success_response, error_response

# 路由层直接返回错误
@router.get("/users/{user_id}")
async def get_user(user_id: int):
    user = await db.get_user(user_id)
    if not user:
        response, _ = error_response("用户不存在", "USER_NOT_FOUND", 404)
        return response
    return success_response(user)
```

## Python 依赖规范

| 依赖包 | 何时需要 |
|--------|---------|
| `email-validator>=2.0` | 使用 `EmailStr` 类型时 |
| `python-jose[cryptography]>=3.3` | JWT 认证 |
| `bcrypt>=4` | 密码哈希（直接使用 `bcrypt.hashpw` / `bcrypt.checkpw`；**禁止使用 passlib**） |
| `aiosqlite>=0.19` | SQLite 异步（开发环境）|
| `asyncpg>=0.27` | PostgreSQL 异步（生产环境）|

**注意**：使用 `EmailStr` 必须安装 `email-validator`，否则运行时报错。
