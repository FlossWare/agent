# GitHub integration

`agent-ai` treats GitHub as a publication/review boundary rather than embedding GitHub credentials or API policy in workers.

## Boundary

```text
trusted parent
  └── GitHubClient
        └── gh CLI
              ├── auth status
              ├── PR create/view
              └── PR merge

worker subprocess
  └── no GitHub credentials
```

The worker performs repository work in a confined worktree. Publication should happen only after deterministic verification and arbiter acceptance, and the caller remains responsible for the authority required to push or merge.

## Usage

```python
from personal_agent.github import GitHubClient

client = GitHubClient("FlossWare/agent")
status = client.status()
pr = client.create_pull_request(
    title="fix: example",
    body="Verification and arbiter evidence are attached to the run record.",
    head="fix/example",
    base="main",
)
print(pr.url)
```

`GitHubClient.merge_pull_request()` is deliberately not called by the worker. Merge is an authorization boundary and must remain an explicit caller operation.

## Authentication

Use the normal `gh auth login` flow or an equivalent `gh` supported credential mechanism in the trusted parent environment. Never place tokens in `Work`, `WorkerResult`, generated instruction files, prompts, or repository files.

For autonomous execution, map GitHub operations to the engineering guardrail levels in the repository's engineering workflow contract. Creating or pushing a branch is publication authority; merging is a separate authorization step.
