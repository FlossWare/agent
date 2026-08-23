# Interactive TUI Setup

personal-agent includes an interactive TUI builder that configures AI coding agents
with FlossWare libraries, budget awareness, and provider selection.

## Quick Start

```bash
python3 scripts/setup.py
```

With a specific theme:

```bash
python3 scripts/setup.py --theme borland-3d
```

For non-interactive environments, use the shell installer:

```bash
./scripts/install.sh --agent all --repo /path/to/project
```

## TUI Walkthrough

### Welcome Screen

Choose your theme or press Enter to start with the default dark theme.
Press `t` to open the live theme picker with preview.

```
                     personal-agent builder



    Build AI coding-agent configs using FlossWare libraries
    github.com/sfloess/personal-agent

    Theme: dark  (press 't' to change, Enter to start)
```

Available themes: dark, light, default, borland-3d, dos, dbase-iii,
dbase-iv, dbase-iv-3d, ti-99-4a, trs-80.

### Step 1/5: Agent Selection

Select which coding agents to configure. Each generates agent-specific config files.

```
                   1/5  Select Coding Agents



    > [x] Claude Code          Terminal, desktop, web, IDE extensions
      [x] Cursor               AI-native IDE with built-in models
      [ ] OpenCode / Codex     Terminal-based coding agents

   Space=toggle  a=all  n=none  Enter=confirm  q=quit
```

| Agent | Generated Files |
|-------|----------------|
| Claude Code | `CLAUDE.md`, `.claude/skills/*.md` |
| Cursor | `.cursorrules` |
| OpenCode | `AGENTS.md` |

### Step 2/5: FlossWare AI Capabilities

Select which FlossWare AI libraries to wire into your configuration.
Core libraries are pre-selected; optional ones add advanced features.

```
                 2/5  FlossWare AI Capabilities



    > [x] model-router-ai         Smart LLM routing with provider failover
      [x] resilience-ai           Retry, circuit breaker, timeout patterns
      [x] structured-output-ai    Schema-validated JSON from LLMs
      [ ] consensus-ai            Multi-model voting for critical decisions
      [ ] evaluation-ai           Quality scoring and adversarial verification
      [ ] observability-ai        Structured logging, metrics, cost tracking
      [ ] security-ai             Input validation, secrets masking, audit logging
      [ ] rag-ai                  Document retrieval and hybrid search
      [ ] genetic-optimizer-ai    Parameter tuning via genetic algorithms

   Space=toggle  a=all  n=none  Enter=confirm  q=quit
```

| Library | Type | What It Adds |
|---------|------|-------------|
| model-router-ai | Core | Provider routing, failover, cost tracking |
| resilience-ai | Core | Retry with backoff, circuit breaker |
| structured-output-ai | Core | JSON schema validation for LLM output |
| consensus-ai | Optional | Multi-model voting, `/pa-consensus` skill |
| evaluation-ai | Optional | Adversarial verification panels |
| observability-ai | Optional | Structured JSON logging, cost tracker |
| security-ai | Optional | Input validation, secrets masking |
| rag-ai | Optional | Document retrieval for context |
| genetic-optimizer-ai | Optional | Parameter optimization |

### Step 3/5: Budget Configuration

Choose your monthly LLM budget. This affects which providers are recommended
and generates appropriate cost constraints in `ai_config.py`.

```
                      3/5  Monthly Budget



    > (o) Free only    Cohere, OpenRouter, Gemini free tiers
      ( ) Light        $10/month   adds Groq, Cerebras fast inference
      ( ) Medium       $50/month   adds Claude Haiku, GPT-4o-mini
      ( ) Custom       Set your own monthly budget

   Up/Down=navigate  Enter=confirm  q=quit
```

### Step 4/5: Project Directory & API Key Status

Enter your project path, then see which provider keys are detected.

```
    Project directory: /home/user/my-project

    API Key Status:

     SET  Cohere       $COHERE_API_KEY
     SET  OpenRouter   $OPENROUTER_API_KEY
     ---  Gemini       $GEMINI_API_KEY
                       https://aistudio.google.com/apikey
```

### Step 5/5: Build & Summary

The builder generates all config files and shows what was created.

```
                         Setup Complete



    Agents:
      + Claude Code
      + Cursor

    AI Stack:
      + model-router-ai
      + resilience-ai
      + structured-output-ai

    Budget: Free only

    Generated files:
      CLAUDE.md          .claude/skills/
      .cursorrules       ai_config.py
      .pa-config.json

    Press Enter to exit
```

## Theme Examples

The TUI supports 10 built-in themes from
[FlossWare/curses-themes](https://github.com/FlossWare/curses-themes).

**dos theme:**
```
+------------ 2/5  FlossWare AI Capabilities [dos] ------------+
|                                                              |
+--------------------------------------------------------------+

    > [x] model-router-ai         Smart LLM routing with provider failover
      [x] resilience-ai           Retry, circuit breaker, timeout patterns
      [x] structured-output-ai    Schema-validated JSON from LLMs
      [ ] consensus-ai            Multi-model voting for critical decisions
      [ ] evaluation-ai           Quality scoring and adversarial verification
```

**trs-80 theme:**
```
+---------- 2/5  FlossWare AI Capabilities [trs-80] -----------+
|                                                              |
+--------------------------------------------------------------+

    > [x] model-router-ai         Smart LLM routing with provider failover
      [x] resilience-ai           Retry, circuit breaker, timeout patterns
      [x] structured-output-ai    Schema-validated JSON from LLMs
```

## Generated Files

All files are written to the project directory specified in Step 4.

### CLAUDE.md
Claude Code instructions with FlossWare library usage, skills, and constraints
matching your selected capabilities and budget.

### .cursorrules
Cursor IDE rules with the same FlossWare configuration and coding standards.

### AGENTS.md
OpenCode/Codex agent instructions with library imports and usage patterns.

### .claude/skills/*.md
Claude Code skill files for each selected capability (e.g., `/pa-consensus`).

### ai_config.py

A Python module wiring selected FlossWare capabilities:

```python
from personal_agent.router import create_free_router
router = create_free_router(max_monthly=0)

from resilience_ai import RetryConfig, CircuitBreaker
RETRY = RetryConfig(max_retries=3, backoff_base=2.0)
```

### .pa-config.json

Build manifest recording your selections (agents, capabilities, budget).
Used by tools to understand the project's AI configuration.

## Keyboard Controls

| Key | Action |
|-----|--------|
| Space | Toggle selection |
| Enter | Confirm |
| Up/Down | Navigate |
| a | Select all |
| n | Select none |
| q | Quit/cancel |
| t | Theme picker (welcome screen) |

## Themes

| Theme | Style |
|-------|-------|
| dark | Modern dark mode |
| light | High contrast light |
| borland-3d | Turbo Vision 3D |
| dos | Classic MS-DOS |
| dbase-iii | Retro database |
| dbase-iv | Windowed database |
| dbase-iv-3d | 3D windowed |
| ti-99-4a | TI home computer |
| trs-80 | Tandy monochrome |
| default | Classic terminal |
