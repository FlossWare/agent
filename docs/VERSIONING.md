# Dependency versioning strategy

## Current policy (0.1 dogfood)

Runtime dependencies in `pyproject.toml` resolve against the default branch
(`HEAD`) of sibling FlossWare libraries:

```toml
"model-router-ai @ git+https://github.com/FlossWare/model-router-ai.git"
"resilience-ai @ git+https://github.com/FlossWare/resilience-ai.git"
"structured-output-ai @ git+https://github.com/FlossWare/structured-output-ai.git"
```

This is intentional for dogfood: libraries move quickly and the stack is
validated as a set. It is **not** suitable for long-lived reproducible deploys.

## FlossWare release versioning

Release-version semantics are defined centrally by **FlossWare Engineering
Standards ADR-0023: Two-Component Release Versioning**.

FlossWare uses exactly two numeric components:

```text
0.1 → 0.2 → 0.3 → ... → 1.0 → 1.1 → 1.2 → ...
```

There are no patch releases. Git commit SHAs remain the precise immutable
source-state identifiers.

## Target dependency policy (0.2+)

1. Tag each FlossWare AI library with a two-component release ref (`v0.2`, etc.).
2. Pin every git dependency to a release tag or full commit SHA:

   ```toml
   "model-router-ai @ git+https://github.com/FlossWare/model-router-ai.git@v0.2"
   ```

3. Document breaking changes in this repository’s release notes / changelog.
4. Prefer the same pin style as `coding-agent-setup` (`FLOSSWARE_RELEASE_REF`).

Until those tags exist, do not invent pin SHAs in production automation without
recording the resolved commit from a known-good install (`pip freeze` /
`pip install` output).

## Audit tips

```bash
pip install -e .
pip list | grep -E 'model-router|resilience|structured-output'
pip freeze | grep FlossWare
```

Record the resolved commit hashes when cutting a dogfood report.
