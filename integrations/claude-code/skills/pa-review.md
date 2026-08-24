---
name: pa-review
description: Run coding-agent-ai arbiter review on current changes
---

Run an independent AI review of the current changes using coding-agent-ai.

Steps:
1. Get the current diff: `git diff`
2. Run coding-agent-ai in investigation mode on the diff:
   ```bash
   pa --investigate "Review these changes for correctness, security issues, and test coverage. Focus on: logic bugs, missing error handling, security vulnerabilities, and incomplete implementations." --repo . --json
   ```
3. Parse the JSON output and present findings to the user grouped by severity
4. If there are HIGH or CRITICAL findings, suggest specific fixes
