---
name: pa-investigate
description: Investigate codebase using coding-agent-ai without making changes
---

Use coding-agent-ai to investigate the codebase without making changes.

When the user asks a question about the codebase:
1. Run investigation:
   ```bash
   pa --investigate "{question}" --repo . --json
   ```
   Replace `{question}` with the user's question.
2. Parse the JSON output
3. Present the plan and findings in a clear format
4. If the investigation suggests changes, list them but do not apply
