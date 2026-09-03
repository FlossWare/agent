"""Composable, provider-neutral FlossWare coding-agent stack.

The core abstraction is capability-oriented: a worker is any capable unit of
work, and an arbiter dispatches work and synthesizes worker evidence. LLMs are
one possible worker implementation, not a requirement of the abstraction.
"""

from personal_agent.capability import CapabilityArbiter, FunctionWorker, Synthesis
from personal_agent.coding_worker import CodingWorkerAdapter
from personal_agent.types import (
    ArbiterDecision,
    CapableWorker,
    CommandResult,
    Decision,
    FileChange,
    Task,
    TaskResult,
    Work,
    WorkerResult,
)
from personal_agent.router import create_router
from personal_agent.worker import Worker
from personal_agent.arbiter import Arbiter
from personal_agent.agent import CodingAgent
from personal_agent.security import (
    CommandPolicy,
    CredentialClass,
    SecretRedactor,
    SecurityError,
    redact_secrets,
    resolve_in_workspace,
    sanitize_worker_environ,
)
from personal_agent.verification import VerificationConfig, VerificationEvidence, evaluate_hard_gates

__version__ = "0.1.0"

__all__ = [
    "Arbiter", "ArbiterDecision", "CapableWorker", "CapabilityArbiter", "CodingAgent",
    "CodingWorkerAdapter", "CommandPolicy", "CommandResult", "CredentialClass", "Decision",
    "FileChange", "FunctionWorker", "SecretRedactor", "SecurityError", "Synthesis", "Task",
    "TaskResult", "VerificationConfig", "VerificationEvidence", "Work", "Worker", "WorkerResult",
    "create_router", "evaluate_hard_gates", "redact_secrets", "resolve_in_workspace",
    "sanitize_worker_environ",
]
