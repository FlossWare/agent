# coding-agent-ai

FlossWare coding-agent execution/orchestration stack built around a provider-neutral **worker / arbiter** architecture.

## Personal MVP

The current practical profile is **FlossWare Personal**:

- free-tier APIs and local models only
- personal credentials isolated under `~/.flossware/ai/personal.env`
- existing `~/.flossware/ai/venv` is reused when present
- no Red Hat credentials or configuration are sourced
- deterministic worker -> hard gates -> independent arbiter loop
- GitHub integration through the user's authenticated `gh` CLI
- Crush integration through generated `~/.config/crush/crushrc`

Thompson Sampling, genetic algorithms, and adaptive model scaling are intentionally deferred from this MVP.

## Install

The standalone bootstrap is intentionally independent of `coding-agent-setup`:

```bash
curl -fsSL https://raw.githubusercontent.com/FlossWare/coding-agent-ai/main/install.sh | bash
```

Then add only personal/free credentials to `~/.flossware/ai/personal.env` and start a new shell (or source the file).

```bash
flossware-ai models
flossware-ai accounts
flossware-ai crush-config --write
```

The installer reuses `~/.flossware/ai/venv` and `~/.flossware/ai` rather than creating another FlossWare installation tree.

## Core model

A **worker is any capable unit of work**. It is not synonymous with an LLM. A worker may be deterministic code, a CLI, MCP capability, another agent, a local model, a hosted model, a test runner, or a composite worker.

```text
Task / PR
   -> workers
       -> local model / free API
       -> deterministic tool
       -> GitHub / MCP capability
   -> hard gates
   -> independent arbiter
   -> accept / reject / feedback
```

## Coding workflow

```bash
cd /path/to/repository
flossware-ai run "Fix the failing authentication test" --repo . --commands pytest --max-iter 3
```

The worker operates in an isolated worktree when possible. Tests and security gates can reject a result independently of model output. The arbiter reviews the resulting diff and feeds actionable rejection feedback back to the worker.

## GitHub workflow

Existing `gh` authentication is reused. No GitHub token is copied into FlossWare configuration.

```bash
flossware-ai github auth
flossware-ai github view 123 --repo FlossWare/coding-agent-ai
flossware-ai github diff 123 --repo FlossWare/coding-agent-ai
flossware-ai github review 123 --repo FlossWare/coding-agent-ai
flossware-ai github review 123 --repo FlossWare/coding-agent-ai --post
```

A PR review runs three focused workers (correctness, security, and tests), followed by an independent arbiter that synthesizes their evidence.

## Crush

Crush is the interactive coding-agent UI. `coding-agent-ai` supplies the Personal free/local provider policy and worker/arbiter/GitHub capabilities.

```bash
flossware-ai crush-config --write
crush
```

Crush's current `crushrc` format is Bash and supports local Ollama plus custom OpenAI-compatible providers, which makes it a clean client for this profile.

## Provider policy

The Personal router only discovers:

- Ollama/local models
- Gemini free tier
- Groq free tier
- Cerebras free tier
- OpenRouter free-model endpoint
- Hugging Face free inference where available
- Z.ai free-tier models where available

Provider free tiers can change. A provider being listed here means the Personal profile is designed for its free tier, not that a provider guarantees unlimited $0 usage.

Paid Anthropic/OpenAI/RH providers are not configured by this profile.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

## License

MIT
