"""
用于服务生命周期管理的状态机。
"""

from enum import Enum
from typing import Callable, Optional

from pycore.core.exceptions import ServiceStateError


class ServiceState(str, Enum):
    """服务执行状态。"""

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class StateMachine:
    """
    用于服务生命周期的简单状态机。

    提供：
    - 状态转换验证
    - 状态变更的回调支持
    - 线程安全的状态访问

    用法：
        sm = StateMachine(initial=ServiceState.IDLE)

        # 定义允许的转换
        sm.add_transition(ServiceState.IDLE, ServiceState.STARTING)
        sm.add_transition(ServiceState.STARTING, ServiceState.RUNNING)

        # 添加回调
        sm.on_enter(ServiceState.RUNNING, lambda: print("Running!"))

        # 转换
        sm.transition(ServiceState.STARTING)
        sm.transition(ServiceState.RUNNING)  # 打印 "Running!"
    """

    # 默认状态转换映射
    DEFAULT_TRANSITIONS: dict[ServiceState, set[ServiceState]] = {
        ServiceState.IDLE: {ServiceState.STARTING},
        ServiceState.STARTING: {ServiceState.RUNNING, ServiceState.ERROR},
        ServiceState.RUNNING: {
            ServiceState.PAUSED,
            ServiceState.STOPPING,
            ServiceState.ERROR,
        },
        ServiceState.PAUSED: {ServiceState.RUNNING, ServiceState.STOPPING},
        ServiceState.STOPPING: {ServiceState.STOPPED, ServiceState.ERROR},
        ServiceState.STOPPED: {ServiceState.IDLE},
        ServiceState.ERROR: {ServiceState.STOPPING, ServiceState.IDLE},
    }

    def __init__(
        self,
        initial: ServiceState = ServiceState.IDLE,
        use_defaults: bool = True,
    ):
        self._state = initial
        self._transitions: dict[ServiceState, set[ServiceState]] = {}
        self._on_enter_callbacks: dict[ServiceState, list[Callable]] = {}
        self._on_exit_callbacks: dict[ServiceState, list[Callable]] = {}

        if use_defaults:
            self._transitions = {k: v.copy() for k, v in self.DEFAULT_TRANSITIONS.items()}

    @property
    def state(self) -> ServiceState:
        """获取当前状态。"""
        return self._state

    @property
    def is_idle(self) -> bool:
        return self._state == ServiceState.IDLE

    @property
    def is_running(self) -> bool:
        return self._state == ServiceState.RUNNING

    @property
    def is_error(self) -> bool:
        return self._state == ServiceState.ERROR

    def add_transition(
        self, from_state: ServiceState, to_state: ServiceState
    ) -> "StateMachine":
        """添加允许的状态转换。"""
        if from_state not in self._transitions:
            self._transitions[from_state] = set()
        self._transitions[from_state].add(to_state)
        return self

    def remove_transition(
        self, from_state: ServiceState, to_state: ServiceState
    ) -> "StateMachine":
        """移除状态转换。"""
        if from_state in self._transitions:
            self._transitions[from_state].discard(to_state)
        return self

    def on_enter(self, state: ServiceState, callback: Callable) -> "StateMachine":
        """注册进入状态的回调。"""
        if state not in self._on_enter_callbacks:
            self._on_enter_callbacks[state] = []
        self._on_enter_callbacks[state].append(callback)
        return self

    def on_exit(self, state: ServiceState, callback: Callable) -> "StateMachine":
        """注册退出状态的回调。"""
        if state not in self._on_exit_callbacks:
            self._on_exit_callbacks[state] = []
        self._on_exit_callbacks[state].append(callback)
        return self

    def can_transition(self, to_state: ServiceState) -> bool:
        """检查转换到给定状态是否允许。"""
        allowed = self._transitions.get(self._state, set())
        return to_state in allowed

    def get_allowed_transitions(self) -> set[ServiceState]:
        """获取从当前状态可以转换到的所有状态。"""
        return self._transitions.get(self._state, set()).copy()

    def transition(
        self,
        to_state: ServiceState,
        *,
        force: bool = False,
    ) -> ServiceState:
        """
        执行状态转换。

        参数：
            to_state: 目标状态
            force: 跳过转换验证

        返回：
            新状态

        抛出：
            ServiceStateError: 如果转换不允许
        """
        if not force and not self.can_transition(to_state):
            raise ServiceStateError(
                f"Cannot transition from '{self._state}' to '{to_state}'",
                from_state=self._state.value,
                to_state=to_state.value,
            )

        # 退出回调
        for callback in self._on_exit_callbacks.get(self._state, []):
            callback()

        previous = self._state
        self._state = to_state

        # 进入回调
        for callback in self._on_enter_callbacks.get(to_state, []):
            callback()

        return previous

    def reset(self, to_state: ServiceState = ServiceState.IDLE) -> None:
        """重置到状态而不进行验证。"""
        self._state = to_state

    def __repr__(self) -> str:
        return f"StateMachine(state={self._state})"
