"""CLI entry point for personal-agent.

Usage:
    pa "Fix the bug in auth.py" --repo /path/to/repo
    pa "Review this repo for correctness" --repo . --max-iter 5
    pa --investigate "What does this codebase do?" --repo .
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

from personal_agent.agent import CodingAgent
from personal_agent.types import Decision, Task


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pa",
        description="Personal AI coding agent (free models only)",
    )
    parser.add_argument(
        "task",
        nargs="?",
        help="Task description (or pipe via stdin)",
    )
    parser.add_argument(
        "--repo", "-r",
        default=".",
        help="Path to git repository (default: current directory)",
    )
    parser.add_argument(
        "--files", "-f",
        nargs="*",
        default=[],
        help="Specific files to focus on",
    )
    parser.add_argument(
        "--commands", "-c",
        nargs="*",
        default=[],
        help="Test commands to run after changes",
    )
    parser.add_argument(
        "--max-iter", "-i",
        type=int,
        default=3,
        help="Maximum worker/arbiter iterations (default: 3)",
    )
    parser.add_argument(
        "--investigate",
        action="store_true",
        help="Investigation only (no arbiter loop)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Auto-commit if accepted",
    )

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    task_desc = args.task
    if not task_desc and not sys.stdin.isatty():
        task_desc = sys.stdin.read().strip()
    if not task_desc:
        parser.error("Task description required (positional arg or stdin)")

    repo_path = os.path.abspath(args.repo)

    task = Task(
        description=task_desc,
        repo_path=repo_path,
        files=args.files or [],
        commands=args.commands or [],
        max_iterations=args.max_iter,
    )

    try:
        agent = CodingAgent(repo_path, max_iterations=args.max_iter)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.investigate:
            result = asyncio.run(agent.investigate_only(task))
            _print_investigation(result, args.json_output)
        else:
            result = asyncio.run(agent.run(task))
            _print_result(result, args.json_output)

            if args.commit and result.decision == Decision.ACCEPT:
                from personal_agent.repo import Repo
                repo = Repo(repo_path)
                repo.git_add()
                repo.git_commit(result.commit_message)
                print("\nCommitted successfully.")

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        logging.exception("Failed")
        sys.exit(1)


def _print_result(result, as_json: bool) -> None:
    if as_json:
        print(json.dumps({
            "decision": result.decision.value,
            "iterations": result.iterations,
            "commit_message": result.commit_message,
            "final_diff": result.final_diff,
            "arbiter_decisions": [
                {
                    "decision": d.decision.value,
                    "confidence": d.confidence,
                    "reason": d.reason,
                    "findings": [
                        {"severity": f.severity, "description": f.description}
                        for f in d.findings
                    ],
                }
                for d in result.arbiter_decisions
            ],
        }, indent=2))
        return

    print(f"\n{'='*60}")
    print(f"RESULT: {result.decision.value.upper()}")
    print(f"Iterations: {result.iterations}")
    print(f"{'='*60}")

    if result.arbiter_decisions:
        last = result.arbiter_decisions[-1]
        print(f"\nConfidence: {last.confidence:.0%}")
        print(f"Reason: {last.reason}")
        if last.findings:
            print(f"\nFindings ({len(last.findings)}):")
            for f in last.findings:
                print(f"  [{f.severity.upper()}] {f.description}")

    if result.final_diff:
        print(f"\nDiff ({len(result.final_diff)} chars):")
        lines = result.final_diff.split("\n")
        for line in lines[:50]:
            print(f"  {line}")
        if len(lines) > 50:
            print(f"  ... ({len(lines) - 50} more lines)")

    if result.commit_message:
        print(f"\nCommit message:\n{result.commit_message}")


def _print_investigation(result, as_json: bool) -> None:
    if as_json:
        print(json.dumps({
            "plan": result.plan,
            "findings": result.findings,
            "changes": len(result.changes),
            "model_used": result.model_used,
        }, indent=2))
        return

    print(f"\nPlan: {result.plan}")
    if result.findings:
        print(f"\nFindings:")
        for f in result.findings:
            print(f"  - {f}")
    if result.changes:
        print(f"\nProposed changes ({len(result.changes)}):")
        for c in result.changes:
            print(f"  {c.action}: {c.path}")


if __name__ == "__main__":
    main()
