"""Offline smoke tests for the Fedora dogfood gate.

These tests deliberately do not call a model or require provider credentials.
They prove the installed package can import, expose its CLI, and construct the
core task type without contacting external AI services.
"""

from __future__ import annotations

import subprocess
import sys

from personal_agent.types import Task


def test_task_construction_is_provider_neutral() -> None:
    task = Task(description="smoke test", repo_path=".", max_iterations=1)
    assert task.description == "smoke test"
    assert task.max_iterations == 1


def test_cli_help_does_not_require_credentials() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "personal_agent.cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "provider-neutral" in result.stdout.lower()
    assert "free models only" not in result.stdout.lower()
