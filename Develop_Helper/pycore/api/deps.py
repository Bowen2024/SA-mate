"""
FastAPI 依赖注入模板。

新项目基于此模板扩展认证、权限等依赖。
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from pycore.integrations.db.session import get_db

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    获取当前用户（示例实现）。

    新项目应替换为实际的 JWT 验证逻辑：
    1. 从 credentials.credentials 提取 token
    2. 验证 token 有效性
    3. 从数据库查询用户信息
    4. 返回用户对象
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # TODO: 替换为实际 JWT 验证
    # from jose import jwt
    # payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    # user_id = payload.get("sub")
    # ...

    return {"id": 1, "username": "demo", "role": "employee"}


async def require_admin(
    user: dict = Depends(get_current_user),
) -> dict:
    """要求管理员权限。"""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
