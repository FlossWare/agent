"""personal-agent: Composable AI coding-agent stack using FlossWare capabilities.

Composes model-router-ai, resilience-ai, and structured-output-ai into
a worker/arbiter loop that can inspect, modify, test, and commit code
in real repositories -- using free models only.
"""

from personal_agent.types import (
    ArbiterDecision,
    Task,
    TaskResult,
    WorkerResult,
)
from personal_agent.router import create_free_router
from personal_agent.worker import Worker
from personal_agent.arbiter import Arbiter
from personal_agent.agent import CodingAgent

__version__ = "0.1.0"

__all__ = [
    "Arbiter",
    "ArbiterDecision",
    "CodingAgent",
    "Task",
    "TaskResult",
    "Worker",
    "WorkerResult",
    "create_free_router",
]
