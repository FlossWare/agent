# Security model

coding-agent-ai treats the coding **worker** as untrusted relative to the host.
Security is enforced by deterministic policy layers, not by prompting the model.

## Trust boundaries

```
┌─────────────────────────────────────────────────────────┐
│  Host process (trusted)                                 │
│  - Router holds provider API keys                       │
│  - CodingAgent orchestrates worktrees + hard gates      │
│  - Arbiter is advisory only after hard gates pass       │
└───────────────┬─────────────────────────────────────────┘
                │ scrubbed env, confined paths, CommandPolicy
┌───────────────▼─────────────────────────────────────────┐
│  Worker subprocess / repo ops (untrusted)               │
│  - No provider credentials                              │
│  - Paths must resolve under workspace root              │
│  - Only allowlisted commands as argv (shell=False)      │
│  - Network denied unless allow_network=True             │
└─────────────────────────────────────────────────────────┘
```

## Filesystem confinement

Every read, write, and delete goes through `resolve_in_workspace()`:

- Absolute paths rejected
- `..` / symlink escapes that leave the workspace rejected
- Null bytes rejected

Command arguments that look like paths are checked the same way when a
workspace is bound to `CommandPolicy`.

## Command policy

`CommandPolicy` is the primary control between LLM-proposed commands and
execution:

| Control | Default |
|---------|---------|
| Execution mode | argv list, `shell=False` |
| Allowlist | common dev tools (pytest, git, python, linters, …) |
| Denylist | shells, sudo, network tools, package managers of the host OS, … |
| Network | **off** (`allow_network=False`) |
| Shell metacharacters | rejected unless `allow_shell=True` |

Policy violations return a failed `CommandResult` with
`Blocked by security policy` and are hard-gate failures.

## Credential classes

| Class | Examples | Visible to worker? |
|-------|----------|--------------------|
| Provider | `GROQ_API_KEY`, `COHERE_API_KEY`, … | **No** |
| Repository | `GITHUB_TOKEN`, `GH_TOKEN` | **No** |
| Cloud | `AWS_*` | **No** |
| Package registry | `NPM_TOKEN`, `PYPI_TOKEN` | **No** |
| SSH | `SSH_AUTH_SOCK` | **No** |
| Application | `*_SECRET`, `*_PASSWORD` patterns | **No** |

`sanitize_worker_environ()` builds the subprocess environment. Provider keys
remain available only to the router in the parent process for LLM calls.

### Production recommendations

1. Inject provider keys via OS keychain or a secret manager into the **parent**
   process only (not into a shared `.env` copied into worker containers).
2. Prefer short-lived tokens where the provider supports them.
3. Run the agent under a least-privilege OS user with no broad cloud roles.
4. Do not mount host SSH agent sockets into worker environments.

## Hard verification gates

Before the LLM arbiter can ACCEPT, `evaluate_hard_gates()` runs:

1. Command exit codes (failed tests)
2. Security policy blocks
3. Path-escape attempts in proposed file changes
4. Python syntax check on changed `.py` files
5. Optional required command substrings (e.g. must have run `pytest`)

Any failure forces `REJECT` with `model_used="hard-gate"`. The arbiter cannot
override these results.

## Disposable worktrees

By default `CodingAgent(use_worktree=True)`:

1. Creates a detached git worktree
2. Runs worker/arbiter there
3. On ACCEPT, applies the diff to the primary tree
4. Always cleans up the worktree (including on failure)

A failed or malicious run cannot leave durable changes in the user’s primary
checkout unless apply succeeds after ACCEPT.

## Secret redaction

`redact_secrets()` / `SecretRedactor` strip common token shapes from logs,
arbiter prompts, feedback, and gathered file context. Disable only in trusted
diagnostic environments:

```python
from personal_agent.security import SecretRedactor
redactor = SecretRedactor(enabled=False)  # diagnostics only
```

## Testing

```bash
pytest tests/test_security.py tests/test_verification.py -v
```

Adversarial cases include path traversal, symlink escape, shell metacharacters,
network tools, credential env leakage, and redaction of representative secrets.
