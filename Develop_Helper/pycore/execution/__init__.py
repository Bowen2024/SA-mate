"""
Execution module for PyCore.

Provides:
- Execution context with contextvars
- Flow-based workflow execution
- Pipeline patterns
"""

from pycore.execution.context import ExecutionContext, execution_context
from pycore.execution.flow import (
    BaseFlow,
    FlowStep,
    FlowResult,
    SequentialFlow,
    ParallelFlow,
)

__all__ = [
    "ExecutionContext",
    "execution_context",
    "BaseFlow",
    "FlowStep",
    "FlowResult",
    "SequentialFlow",
    "ParallelFlow",
]
