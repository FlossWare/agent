---
name: pa-fix
description: Use personal-agent worker/arbiter loop to fix an issue
---

Use the full personal-agent worker/arbiter loop to fix an issue.

When the user provides a task description:
1. Run the full loop:
   ```bash
   pa "{task_description}" --repo . -c "{test_commands}" --max-iter 3 --json
   ```
   Replace `{task_description}` with the user's request.
   Replace `{test_commands}` with appropriate test commands (e.g., `pytest tests/`).
2. Parse the JSON output
3. If ACCEPTED: show the diff and commit message, ask if the user wants to commit
4. If REJECTED: show the arbiter's findings and required changes, ask if the user wants to retry with more iterations
