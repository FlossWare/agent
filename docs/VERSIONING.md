# Dependency versioning strategy

## Current policy (0.1 dogfood)

Runtime dependencies in `pyproject.toml` currently resolve against the default branch of sibling FlossWare libraries. This is intentional while the stack is validated as a set, but it is not suitable for long-lived reproducible deployments.

## Target policy (0.2+)

1. Tag each FlossWare AI library with the project's two-component release version (`v0.2`, `v0.3`, etc.).
2. Pin every git dependency to a release tag or full commit SHA.
3. Record resolved SHAs in dogfood/release reports.
4. Keep dependency changes and breaking changes documented in release notes.
5. Prefer the same release-ref mechanism used by `agent-setup`.

Until sibling release tags exist, do not invent version pins. A known commit SHA is preferable to an unrecorded moving target when reproducibility is required.

## Audit

```bash
pip list | grep -E 'model-router|resilience|structured-output'
pip freeze | grep FlossWare
```

Git commit SHAs remain the immutable source-state identifiers even when release tags are used.
