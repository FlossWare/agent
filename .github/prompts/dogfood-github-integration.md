# Dogfood: GitHub integration boundary

Validate the repository publication path without moving credentials into worker state.

## Acceptance criteria

1. The worker and arbiter remain provider-neutral.
2. GitHub authentication is supplied only by the trusted parent environment or `gh` credential store.
3. `GitHubClient` does not store, serialize, or write credentials to task state, worker results, prompts, or repository files.
4. CI proves `GH_TOKEN`/`GITHUB_TOKEN` remains available to the `gh` subprocess.
5. Pull-request creation, inspection, and squash merge remain explicit operations.
6. Merge authorization remains outside the worker/arbiter decision itself.

## Dogfood sequence

`Task -> Worker -> hard gates -> Arbiter -> accepted diff -> trusted GitHub publication`

A live publication run must use a disposable branch and an explicitly authorized GitHub identity. Tests must use mocked `gh` subprocesses and must never require a real token.
