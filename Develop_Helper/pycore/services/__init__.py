"""
Service layer for PyCore.

提供三层服务架构：
- SimpleService: 轻量级，无状态机
- BaseService: 基础状态机（3 状态）
- AgentService: AI Agent 专用，完整功能（7 状态 + 卡死检测）
"""

from pycore.services.state import ServiceState, StateMachine
from pycore.services.simple import SimpleService
from pycore.services.base import BaseService, SimpleState
from pycore.services.agent import AgentService, AgentContext

# 向后兼容别名
ServiceContext = AgentContext

__all__ = [
    # States
    "ServiceState",
    "StateMachine",
    "SimpleState",
    # Services
    "SimpleService",
    "BaseService",
    "AgentService",
    # Contexts
    "AgentContext",
    "ServiceContext",  # 向后兼容
]
