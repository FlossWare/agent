# Security model

`coding-agent-ai` treats the coding **worker** as untrusted relative to the host.
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

Writes into `.git` metadata, including hooks, are prohibited. This prevents a
worker from creating executable Git hooks that could run outside the command
policy during later Git operations.

## Command policy

`CommandPolicy` is the primary control between LLM-proposed commands and
execution. See [COMMAND-POLICY.md](COMMAND-POLICY.md) for the threat model and
regression-test matrix.

| Control | Default |
|---------|---------|
| Execution mode | argv list, `shell=False` |
| Allowlist | common dev tools (pytest, git, python, linters, …) |
| Denylist | shells, sudo, network tools, package managers of the host OS, … |
| Network | **off** (`allow_network=False`) |
| Shell metacharacters | rejected unless `allow_shell=True` |

Policy violations return a failed `CommandResult` with
`Blocked by security policy` and are hard-gate failures.

The command policy is intentionally capability-oriented. Enabling network or
shell execution is an explicit policy decision and must not be inferred from
model output.

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

The security invariant is stronger than "the worker should not normally see a
secret": configured credentials must not be available through the worker's
environment, repository mounts, command output, generated files, diffs, logs,
feedback, or arbiter input. Tests should treat attempted credential
exfiltration as an adversarial case.

### Production recommendations

1. Inject provider keys via OS keychain or a secret manager into the **parent**
   process only (not into a shared `.env` copied into worker containers).
2. Prefer short-lived tokens where the provider supports them.
3. Run the agent under a least-privilege OS user with no broad cloud roles.
4. Do not mount host SSH agent sockets into worker environments.
5. Treat model/provider choice as a routing and policy concern; this project is
   provider-agnostic and does not require free-only models.

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

The `personal_agent` import is currently retained as a compatibility API while
the distribution/repository identity is `coding-agent-ai`.

## Testing

```bash
pytest tests/test_security.py tests/test_verification.py -v
```

Adversarial cases include path traversal, symlink escape, shell metacharacters,
network tools, credential env leakage, and redaction of representative secrets.
The command-policy threat model in [COMMAND-POLICY.md](COMMAND-POLICY.md) is the
minimum regression matrix for security-sensitive command handling.
