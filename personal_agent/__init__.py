"""Composable, provider-neutral FlossWare coding-agent stack.

The core abstraction is capability-oriented: a worker is any capable unit of
work, and an arbiter dispatches work and synthesizes worker evidence. LLMs are
one possible worker implementation, not a requirement of the abstraction.
"""

from personal_agent.capability import CapableWorker, CapabilityArbiter, FunctionWorker, Synthesis, Work
from personal_agent.types import ArbiterDecision, Decision, FileChange, CommandResult, Task, TaskResult, WorkerResult
from personal_agent.router import create_router
from personal_agent.worker import Worker
from personal_agent.arbiter import Arbiter
from personal_agent.agent import CodingAgent
from personal_agent.model_fabric import (
    Account, Model, ModelWorker, Provider, WorkerPool, WorkerStatus,
    load_worker_config, workers_from_config,
)
from personal_agent.security import CommandPolicy, CredentialClass, SecretRedactor, SecurityError, redact_secrets, resolve_in_workspace, sanitize_worker_environ
from personal_agent.verification import VerificationConfig, VerificationEvidence, evaluate_hard_gates

__version__ = "0.1.0"

__all__ = [
    "Account", "Arbiter", "ArbiterDecision", "CapableWorker", "CapabilityArbiter", "CodingAgent",
    "CommandPolicy", "CommandResult", "CredentialClass", "Decision", "FileChange",
    "FunctionWorker", "Model", "ModelWorker", "Provider", "SecretRedactor", "SecurityError",
    "Synthesis", "Task", "TaskResult", "VerificationConfig", "VerificationEvidence",
    "Worker", "WorkerPool", "WorkerResult", "WorkerStatus", "Work", "create_router",
    "evaluate_hard_gates", "load_worker_config", "redact_secrets", "resolve_in_workspace",
    "sanitize_worker_environ", "workers_from_config",
]
