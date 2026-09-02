# Historical: personal-agent → coding-agent-ai → agent-ai

This document records the repository/project rename history. It is retained for historical reference and is not a current installation guide.

## Rename history

| Stage | Repository / project name |
|---|---|
| Original | `FlossWare/personal-agent` |
| Intermediate | `FlossWare/coding-agent-ai` |
| Current | `FlossWare/agent-ai` |

The Python import package remains `personal_agent` for API compatibility. The CLI entry point remains `pa` unless and until a separately documented breaking change is made.

The setup/control-plane project is now `FlossWare/agent-setup`.

## Historical installation references

Older installation and checkout examples referenced `coding-agent-ai`. They are preserved here only to explain the migration history. New documentation must use `agent-ai` and `agent-setup`.

## Current architecture

- `agent-ai`: provider-neutral execution/orchestration, workers, arbitration, iteration, and engineering workflow.
- `agent-setup`: installation, profiles, configuration, discovery, diagnostics, and external-agent setup.
- `model-router-ai`: provider/account/model routing.
- `consensus-ai`: reusable consensus/arbitration strategies.
- `crush-demo`: integration and acceptance harness.
