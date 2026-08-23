"""Worker: Investigates repositories and proposes/implements changes.

A worker receives a Task, inspects the repository, formulates a plan,
makes changes, runs tests, and returns a WorkerResult.

Commands proposed by the model are validated by CommandPolicy before
execution. Provider credentials are never present in the worker
subprocess environment.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from personal_agent.repo import Repo
from personal_agent.security import CommandPolicy, SecurityError, redact_secrets
from personal_agent.types import (
    CommandResult,
    FileChange,
    Task,
    WorkerResult,
)

logger = logging.getLogger(__name__)

INVESTIGATION_PROMPT = """You are a senior software engineer investigating a repository.

TASK: {task_description}

REPOSITORY STRUCTURE:
{tree}

{file_contents}

GIT STATUS:
{git_status}

{extra_context}

Investigate the repository and respond with a JSON object:
{{
    "plan": "Brief description of your approach",
    "findings": ["finding 1", "finding 2", ...],
    "changes": [
        {{
            "path": "relative/path/to/file.py",
            "action": "modify",
            "content": "full new file content",
            "reason": "why this change"
        }}
    ],
    "commands_to_run": ["pytest tests/", "python -m py_compile src/main.py"]
}}

Be specific. Return actual file contents, not placeholders.
If no changes are needed, return empty changes array with findings explaining why.
Only propose safe development commands (pytest, python, git, linters). Do not
propose shell pipelines, network tools, or system administration commands.
"""

FIX_PROMPT = """You are a senior software engineer fixing code based on reviewer feedback.

TASK: {task_description}

PREVIOUS ATTEMPT FEEDBACK:
{feedback}

CURRENT REPOSITORY STATE:
{tree}

{file_contents}

GIT DIFF (your previous changes):
{git_diff}

TEST RESULTS:
{test_results}

Fix the issues identified by the reviewer. Respond with JSON:
{{
    "plan": "Brief description of fixes",
    "findings": ["what you fixed and why"],
    "changes": [
        {{
            "path": "relative/path/to/file.py",
            "action": "modify",
            "content": "full corrected file content",
            "reason": "why this change"
        }}
    ],
    "commands_to_run": ["pytest tests/"]
}}
"""


class Worker:
    """Executes coding tasks against a repository.

    Uses an LLM to investigate, plan, and implement changes.
    All commands pass through CommandPolicy; all paths through
    workspace confinement.
    """

    def __init__(
        self,
        router: Any,
        repo: Repo,
        *,
        policy: CommandPolicy | None = None,
    ) -> None:
        self._router = router
        self._repo = repo
        self._policy = policy or repo.policy

    async def investigate(self, task: Task) -> WorkerResult:
        """Investigate the repo and propose/implement changes."""
        tree = self._repo.tree()
        file_contents = self._gather_file_contents(task)
        git_status = self._repo.git_status()
        extra = ""
        if task.context:
            extra = "ADDITIONAL CONTEXT:\n" + json.dumps(task.context, indent=2)

        prompt = INVESTIGATION_PROMPT.format(
            task_description=task.description,
            tree=tree,
            file_contents=file_contents,
            git_status=git_status,
            extra_context=extra,
        )

        return await self._execute_prompt(prompt, task)

    async def fix(self, task: Task, feedback: str, previous: WorkerResult) -> WorkerResult:
        """Fix issues based on arbiter feedback."""
        tree = self._repo.tree()
        file_contents = self._gather_file_contents(task)
        git_diff = redact_secrets(self._repo.git_diff())
        test_results = "\n".join(
            f"$ {r.command}\n{redact_secrets(r.stdout)}\n{redact_secrets(r.stderr)}"
            for r in previous.test_results
        )

        prompt = FIX_PROMPT.format(
            task_description=task.description,
            feedback=redact_secrets(feedback),
            tree=tree,
            file_contents=file_contents,
            git_diff=git_diff,
            test_results=test_results or "(no test results)",
        )

        return await self._execute_prompt(prompt, task)

    async def _execute_prompt(self, prompt: str, task: Task) -> WorkerResult:
        """Send prompt to LLM, parse response, apply changes, run commands."""
        resp = await self._router.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=8192,
        )

        parsed = self._parse_response(resp.content)

        changes = []
        for c in parsed.get("changes", []):
            changes.append(FileChange(
                path=c["path"],
                action=c.get("action", "modify"),
                content=c.get("content", ""),
            ))

        if changes:
            self._repo.apply_changes(changes)

        test_results: list[CommandResult] = []
        for cmd in parsed.get("commands_to_run", []):
            if not cmd:
                continue
            test_results.append(self._run_safe(cmd))

        for cmd in task.commands:
            test_results.append(self._run_safe(cmd))

        return WorkerResult(
            plan=parsed.get("plan", ""),
            findings=parsed.get("findings", []),
            changes=changes,
            test_results=test_results,
            model_used=getattr(resp, "model", ""),
            raw_response=resp.content,
        )

    def _run_safe(self, cmd: str) -> CommandResult:
        """Run a command under policy; always return a CommandResult."""
        return self._repo.run_command(cmd, timeout=60, policy=self._policy)

    def _gather_file_contents(self, task: Task) -> str:
        """Read relevant files for context."""
        files_to_read = task.files or self._repo.list_files()[:20]
        parts = []
        for f in files_to_read:
            try:
                content = self._repo.read_file(f)
                if len(content) > 10000:
                    content = content[:10000] + "\n... (truncated)"
                parts.append(f"=== {f} ===\n{redact_secrets(content)}")
            except (SecurityError, FileNotFoundError, IsADirectoryError, OSError):
                continue
        return "\n\n".join(parts)

    def _parse_response(self, text: str) -> dict:
        """Extract JSON from LLM response."""
        text = text.strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0]

        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            candidate = text[start:end]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                fixed = self._fix_malformed_json(candidate)
                if fixed is not None:
                    return fixed

        return {"plan": text, "findings": [], "changes": [], "commands_to_run": []}

    @staticmethod
    def _fix_malformed_json(text: str) -> dict | None:
        """Handle common LLM JSON mistakes like triple-quoted strings."""
        import re

        def _replace_triple_quote(m: re.Match) -> str:
            inner = m.group(1)
            inner = inner.replace('\\"', '"')
            return json.dumps(inner)

        fixed = re.sub(r'"""(.*?)"""', _replace_triple_quote, text, flags=re.DOTALL)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        fixed2 = re.sub(r',\s*([}\]])', r'\1', fixed)
        try:
            return json.loads(fixed2)
        except json.JSONDecodeError:
            return None
