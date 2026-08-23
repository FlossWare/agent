#!/usr/bin/env python3
"""Interactive TUI builder for personal-agent configurations.

Uses FlossWare/curses-themes for professional theming.
Lets users select agents, FlossWare AI capabilities, budget,
and generates custom agent configs wired to those libraries.

Usage:
    python3 scripts/setup.py
    python3 scripts/setup.py --theme borland-3d
    python3 scripts/setup.py --theme dos
"""

import curses
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

PA_REPO = "https://github.com/sfloess/personal-agent.git"

# --- Data Models ---

AGENTS = [
    ("Claude Code", "claude-code", "Terminal, desktop, web, IDE extensions"),
    ("Cursor", "cursor", "AI-native IDE with built-in models"),
    ("OpenCode / Codex", "opencode", "Terminal-based coding agents"),
]

CAPABILITIES = [
    ("model-router-ai", "Smart LLM routing with provider failover", True),
    ("resilience-ai", "Retry, circuit breaker, timeout patterns", True),
    ("structured-output-ai", "Schema-validated JSON from LLMs", True),
    ("consensus-ai", "Multi-model voting for critical decisions", False),
    ("evaluation-ai", "Quality scoring and adversarial verification", False),
    ("observability-ai", "Structured logging, metrics, cost tracking", False),
    ("security-ai", "Input validation, secrets masking, audit logging", False),
    ("rag-ai", "Document retrieval and hybrid search", False),
    ("genetic-optimizer-ai", "Parameter tuning via genetic algorithms", False),
]

BUDGET_TIERS = [
    ("Free only", 0, "Cohere, OpenRouter, Gemini free tiers"),
    ("Light", 10, "$10/month — adds Groq, Cerebras fast inference"),
    ("Medium", 50, "$50/month — adds Claude Haiku, GPT-4o-mini"),
    ("Custom", -1, "Set your own monthly budget"),
]

PROVIDERS = [
    ("Cohere", "COHERE_API_KEY", "https://dashboard.cohere.com/api-keys", True),
    ("OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/keys", True),
    ("Gemini", "GEMINI_API_KEY", "https://aistudio.google.com/apikey", True),
    ("Groq", "GROQ_API_KEY", "https://console.groq.com/keys", False),
    ("Cerebras", "CEREBRAS_API_KEY", "https://cerebras.ai", False),
    ("HuggingFace", "HUGGINGFACE_API_KEY", "https://huggingface.co/settings/tokens", False),
]


@dataclass
class BuildConfig:
    agents: list = field(default_factory=list)
    capabilities: list = field(default_factory=list)
    budget_tier: int = 0
    budget_amount: float = 0.0
    providers: list = field(default_factory=list)
    repo_dir: str = "."
    theme_name: str = "dark"


# --- Theme ---

theme = None


def load_theme(name="dark"):
    global theme
    try:
        from curses_themes import ThemeManager
        theme = ThemeManager.load(name)
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "git+https://github.com/FlossWare/curses-themes.git"],
            capture_output=True, timeout=120, check=True,
        )
        from curses_themes import ThemeManager
        theme = ThemeManager.load(name)
    return theme


# --- Drawing Helpers ---

def draw_header(win, y, title):
    h, w = win.getmaxyx()
    box_w = min(w - 2, 64)
    if box_w >= 10 and y + 4 < h:
        theme.draw_box(win, y, 0, 3, box_w, title=title)
        return y + 3
    win.addstr(y, 0, f" {title} ",
               curses.color_pair(theme.colors.primary) | curses.A_BOLD)
    return y + 1


def draw_status(win, y, text, kind="info"):
    h, w = win.getmaxyx()
    if y >= h - 1:
        return
    color_id = getattr(theme.colors, kind, theme.colors.info)
    win.addstr(y, 2, text[:w - 3], curses.color_pair(color_id))


def draw_progress(win, y, current, total, width=40):
    h, w = win.getmaxyx()
    if y >= h - 1:
        return
    bar_w = min(width, w - 10)
    filled = int(bar_w * current / max(total, 1))
    bar = "█" * filled + "░" * (bar_w - filled)
    pct = f" {current}/{total}"
    win.addstr(y, 2, bar, curses.color_pair(theme.colors.primary))
    win.addstr(y, 2 + bar_w, pct, curses.color_pair(theme.colors.info))


# --- Screens ---

def checkbox_menu(win, title, items, preselected=None, show_desc=True):
    """Generic checkbox menu. items = [(name, key, desc), ...] or [(name, key, desc, default)]."""
    if preselected is not None:
        selected = set(preselected)
    else:
        selected = set()
        for i, item in enumerate(items):
            if len(item) > 3 and item[3]:
                selected.add(i)
            elif len(item) <= 3:
                selected.add(i)

    cursor = 0
    h, w = win.getmaxyx()

    while True:
        win.erase()
        y = draw_header(win, 0, title)
        y += 1

        for i, item in enumerate(items):
            if y >= h - 3:
                break
            name = item[0]
            desc = item[2] if show_desc and len(item) > 2 else ""
            check = "[x]" if i in selected else "[ ]"
            prefix = " > " if i == cursor else "   "

            if i == cursor:
                win.addstr(y, 0, prefix,
                           curses.color_pair(theme.colors.primary) | curses.A_BOLD)
                win.addstr(y, 3, check,
                           curses.color_pair(theme.colors.success if i in selected else theme.colors.warning))
                win.addstr(y, 7, name,
                           curses.color_pair(theme.components.selection))
            else:
                win.addstr(y, 0, prefix)
                win.addstr(y, 3, check,
                           curses.color_pair(theme.colors.success if i in selected else theme.colors.foreground))
                win.addstr(y, 7, name, curses.A_BOLD)

            if desc:
                dx = 7 + len(name) + 2
                if dx + len(desc) < w:
                    win.addstr(y, dx, desc, curses.color_pair(theme.colors.info))
            y += 1

        y += 1
        if y < h - 1:
            win.addstr(y, 2, "Space:toggle  Enter:confirm  a:all  n:none  q:quit",
                       curses.color_pair(theme.colors.accent))

        win.refresh()
        key = win.getch()

        if key == ord(" "):
            selected.symmetric_difference_update({cursor})
        elif key == curses.KEY_UP and cursor > 0:
            cursor -= 1
        elif key == curses.KEY_DOWN and cursor < len(items) - 1:
            cursor += 1
        elif key == ord("a"):
            selected = set(range(len(items)))
        elif key == ord("n"):
            selected.clear()
        elif key in (curses.KEY_ENTER, 10, 13):
            return sorted(selected)
        elif key == ord("q"):
            return None


def radio_menu(win, title, items):
    """Single-select radio menu. items = [(name, value, desc), ...]."""
    cursor = 0
    h, w = win.getmaxyx()

    while True:
        win.erase()
        y = draw_header(win, 0, title)
        y += 1

        for i, (name, _, desc) in enumerate(items):
            if y >= h - 3:
                break
            radio = "(o)" if i == cursor else "( )"
            prefix = " > " if i == cursor else "   "

            if i == cursor:
                win.addstr(y, 0, prefix,
                           curses.color_pair(theme.colors.primary) | curses.A_BOLD)
                win.addstr(y, 3, radio,
                           curses.color_pair(theme.colors.success))
                win.addstr(y, 7, name,
                           curses.color_pair(theme.components.selection))
            else:
                win.addstr(y, 0, prefix)
                win.addstr(y, 3, radio,
                           curses.color_pair(theme.colors.foreground))
                win.addstr(y, 7, name, curses.A_BOLD)

            dx = 7 + len(name) + 2
            if dx + len(desc) < w:
                win.addstr(y, dx, desc, curses.color_pair(theme.colors.info))
            y += 1

        y += 1
        if y < h - 1:
            win.addstr(y, 2, "Enter:select  q:quit",
                       curses.color_pair(theme.colors.accent))

        win.refresh()
        key = win.getch()

        if key == curses.KEY_UP and cursor > 0:
            cursor -= 1
        elif key == curses.KEY_DOWN and cursor < len(items) - 1:
            cursor += 1
        elif key in (curses.KEY_ENTER, 10, 13):
            return cursor
        elif key == ord("q"):
            return None


def text_input(win, prompt, default=""):
    win.erase()
    y = draw_header(win, 0, "Configuration")
    y += 1
    win.addstr(y, 2, prompt, curses.color_pair(theme.colors.foreground))
    y += 1
    win.addstr(y, 2, f"[{default}]: ", curses.color_pair(theme.colors.info))

    curses.echo()
    curses.curs_set(1)
    inp_x = 2 + len(f"[{default}]: ")
    value = win.getstr(y, inp_x, 200).decode().strip()
    curses.noecho()
    curses.curs_set(0)

    return value if value else default


def theme_picker(win):
    from curses_themes import ThemeManager
    all_themes = list(ThemeManager.list_themes().keys())
    items = [(name, name, "") for name in all_themes]

    cursor = 0
    current_preview = all_themes[0] if all_themes else "dark"
    h, w = win.getmaxyx()

    while True:
        preview_theme = ThemeManager.load(all_themes[cursor])
        preview_theme.apply(win)

        win.erase()
        y = preview_theme.draw_box(win, 0, 0, 3, min(w - 2, 50),
                                   title="Choose Theme") or 3
        if isinstance(y, type(None)):
            y = 3
        y = 4

        for i, name in enumerate(all_themes):
            if y >= h - 6:
                break
            prefix = " > " if i == cursor else "   "
            if i == cursor:
                win.addstr(y, 0, prefix,
                           curses.color_pair(preview_theme.colors.primary) | curses.A_BOLD)
                win.addstr(y, 3, name,
                           curses.color_pair(preview_theme.components.selection))
            else:
                win.addstr(y, 0, prefix)
                win.addstr(y, 3, name, curses.A_BOLD)
            y += 1

        y += 1
        if y + 4 < h:
            preview_theme.draw_box(win, y, 2, 4, min(w - 4, 50), title="Preview")
            if y + 1 < h:
                win.addstr(y + 1, 4, "Success message",
                           curses.color_pair(preview_theme.colors.success))
            if y + 2 < h:
                win.addstr(y + 2, 4, "Error message",
                           curses.color_pair(preview_theme.colors.error))
            y += 5

        if y < h - 1:
            win.addstr(y, 2, "Enter:select  q:keep current",
                       curses.color_pair(preview_theme.colors.accent))

        win.refresh()
        key = win.getch()

        if key == curses.KEY_UP and cursor > 0:
            cursor -= 1
        elif key == curses.KEY_DOWN and cursor < len(all_themes) - 1:
            cursor += 1
        elif key in (curses.KEY_ENTER, 10, 13):
            return all_themes[cursor]
        elif key == ord("q"):
            return None


def api_key_screen(win, cfg):
    win.erase()
    h, w = win.getmaxyx()
    y = draw_header(win, 0, "API Key Status")
    y += 1

    budget_label = BUDGET_TIERS[cfg.budget_tier][0]
    is_free = cfg.budget_tier == 0
    win.addstr(y, 2, f"Budget: {budget_label}",
               curses.color_pair(theme.colors.primary) | curses.A_BOLD)
    y += 1
    if is_free:
        win.addstr(y, 2, "Only free-tier providers shown",
                   curses.color_pair(theme.colors.warning))
    y += 2

    found = 0
    for name, env_var, url, is_free_tier in PROVIDERS:
        if y >= h - 4:
            break
        if is_free and not is_free_tier:
            continue
        has_key = bool(os.environ.get(env_var, ""))
        if has_key:
            found += 1
            win.addstr(y, 2, " SET ", curses.color_pair(theme.colors.success) | curses.A_BOLD)
        else:
            win.addstr(y, 2, " --- ", curses.color_pair(theme.colors.warning))
        win.addstr(y, 7, f" {name:<12}", curses.A_BOLD)
        env_display = f"${env_var}"
        win.addstr(y, 20, env_display[:w - 21],
                   curses.color_pair(theme.colors.foreground))
        if not has_key:
            y += 1
            if y < h - 4:
                win.addstr(y, 9, url[:w - 10],
                           curses.color_pair(theme.colors.info))
        y += 1

    y += 1
    if found == 0 and y < h - 2:
        draw_status(win, y, "No API keys set! At least one is required.", "error")
        y += 1
        if y < h - 1:
            win.addstr(y, 4, "export COHERE_API_KEY=your-key",
                       curses.color_pair(theme.colors.info))
    elif y < h - 1:
        draw_status(win, y, f"{found} provider(s) configured", "success")

    y += 2
    if y < h - 1:
        win.addstr(y, 2, "Press any key to continue...",
                   curses.color_pair(theme.colors.accent))
    win.refresh()
    win.getch()


# --- Config Generators ---

def generate_claude_md(cfg):
    caps = [CAPABILITIES[i] for i in cfg.capabilities]
    cap_names = [c[0] for c in caps]
    budget = BUDGET_TIERS[cfg.budget_tier]

    sections = [
        "## Personal Agent Integration\n",
        "This project uses [personal-agent](https://github.com/sfloess/personal-agent) ",
        "for AI-assisted development with free LLM models.\n",
    ]

    sections.append("\n### FlossWare AI Stack\n")
    for name, desc, _ in caps:
        sections.append(f"- **{name}**: {desc}\n")

    sections.append(f"\n### Budget: {budget[0]}")
    if budget[1] > 0:
        sections.append(f" (${budget[1]}/month)")
    sections.append("\n")

    if "model-router-ai" in cap_names:
        sections.append("\n### Routing\n")
        sections.append("model-router-ai handles provider selection and failover.\n")
        sections.append("Configured providers (set via environment variables):\n")
        for name, env, _, _ in PROVIDERS:
            if os.environ.get(env):
                sections.append(f"- {name} (`{env}`): active\n")
            else:
                sections.append(f"- {name} (`{env}`): not set\n")

    sections.append("\n### Skills\n\n")
    sections.append("- `/pa-review` — Independent arbiter review of changes\n")
    sections.append("- `/pa-fix` — Worker/arbiter loop to fix an issue\n")
    sections.append("- `/pa-investigate` — Read-only investigation\n")

    if "consensus-ai" in cap_names:
        sections.append("- `/pa-consensus` — Multi-model vote on a decision\n")

    sections.append("\n### Quick Start\n\n```bash\n")
    sections.append("# Install\n")
    install_extras = _pip_extras(cap_names)
    sections.append(f'pip install "git+{PA_REPO}"{install_extras}\n\n')
    sections.append('# Review changes\npa --investigate "Review my changes" --repo .\n\n')
    sections.append('# Fix a bug\npa "Fix the auth bug" --repo . -c "pytest"\n')
    sections.append("```\n")

    sections.append("\n### Python API\n\n```python\n")
    sections.append("import asyncio\n")
    sections.append("from personal_agent import CodingAgent, Task, Decision\n\n")

    if "observability-ai" in cap_names:
        sections.append("from observability_ai import configure_logging\n")
        sections.append("configure_logging(level='INFO', json_output=True)\n\n")

    if "security-ai" in cap_names:
        sections.append("from security_ai import validate_config, mask_secrets\n\n")

    sections.append("async def main():\n")
    sections.append('    agent = CodingAgent(".")\n')
    sections.append("    result = await agent.run(Task(\n")
    sections.append('        description="Fix the failing test",\n')
    sections.append('        commands=["pytest tests/"],\n')
    sections.append("    ))\n")
    sections.append("    if result.decision == Decision.ACCEPT:\n")
    sections.append("        print(result.final_diff)\n\n")
    sections.append("asyncio.run(main())\n```\n")

    if "resilience-ai" in cap_names:
        sections.append("\n### Resilience\n\n")
        sections.append("resilience-ai provides automatic retry with exponential backoff,\n")
        sections.append("circuit breaker for flaky providers, and timeout management.\n")
        sections.append("These are applied automatically via model-router-ai decorators.\n")

    if "evaluation-ai" in cap_names:
        sections.append("\n### Evaluation\n\n")
        sections.append("evaluation-ai provides adversarial verification panels.\n")
        sections.append("Use for critical code reviews:\n\n```bash\n")
        sections.append('pa "Review auth module for security" --repo . --evaluate\n```\n')

    return "".join(sections)


def generate_cursorrules(cfg):
    caps = [CAPABILITIES[i] for i in cfg.capabilities]
    cap_names = [c[0] for c in caps]
    budget = BUDGET_TIERS[cfg.budget_tier]

    lines = [
        "# Cursor Rules — personal-agent integration",
        "",
        "## AI Stack",
        f"Budget: {budget[0]}",
        "Libraries: " + ", ".join(cap_names),
        "",
        "## Commands",
        '- Review: `pa --investigate "Review changes" --repo .`',
        '- Fix: `pa "Fix the bug" --repo . -c "pytest"`',
        '- Investigate: `pa --investigate "Explain this module" --repo .`',
        "",
        "## Providers",
    ]

    for name, env, _, _ in PROVIDERS:
        status = "active" if os.environ.get(env) else "not set"
        lines.append(f"- {name} (${env}): {status}")

    lines.append("")
    lines.append("## Guidelines")
    lines.append("- Use personal-agent for independent code review before committing")
    lines.append("- All LLM calls go through free-tier providers")
    lines.append("- Multiple provider keys enable automatic failover")

    if "consensus-ai" in cap_names:
        lines.append("- Use multi-model consensus for critical decisions")
    if "security-ai" in cap_names:
        lines.append("- Run security validation on user-facing input handlers")
    if "observability-ai" in cap_names:
        lines.append("- Enable structured logging for LLM call tracing")

    lines.append("")
    return "\n".join(lines) + "\n"


def generate_agents_md(cfg):
    caps = [CAPABILITIES[i] for i in cfg.capabilities]
    cap_names = [c[0] for c in caps]
    budget = BUDGET_TIERS[cfg.budget_tier]

    lines = [
        "## Personal Agent",
        "",
        "AI coding agent using free-tier LLM models.",
        f"Budget: {budget[0]}. Stack: {', '.join(cap_names)}.",
        "",
        "### Commands",
        "",
        "```bash",
        'pa "Fix the failing test" --repo . -c "pytest tests/"',
        'pa --investigate "What are the main components?" --repo .',
        'pa "Add input validation" --repo . --commit',
        "```",
        "",
        "### Capabilities",
        "",
    ]

    for name, desc, _ in caps:
        lines.append(f"- **{name}**: {desc}")

    lines.append("")
    lines.append("### Providers")
    lines.append("")

    for name, env, _, _ in PROVIDERS:
        status = "active" if os.environ.get(env) else "not set"
        lines.append(f"- {name} (`{env}`): {status}")

    lines.append("")
    lines.append("### Workflow")
    lines.append("")
    lines.append("1. Worker receives task, inspects repo, proposes changes, runs tests")
    lines.append("2. Arbiter independently reviews (accept/reject with findings)")
    lines.append("3. On rejection, worker retries with structured feedback")
    lines.append("4. On acceptance, changes are ready to commit")
    lines.append("")

    return "\n".join(lines) + "\n"


def generate_ai_config(cfg):
    """Generate a Python config file wiring selected capabilities."""
    caps = [CAPABILITIES[i] for i in cfg.capabilities]
    cap_names = [c[0] for c in caps]
    budget = BUDGET_TIERS[cfg.budget_tier]

    lines = [
        '"""Auto-generated personal-agent configuration.',
        "",
        f"Budget: {budget[0]}",
        f"Capabilities: {', '.join(cap_names)}",
        f"Generated by: python3 scripts/setup.py --theme {cfg.theme_name}",
        '"""',
        "",
        "import os",
        "",
    ]

    lines.append("# Budget")
    lines.append(f"MONTHLY_BUDGET = {budget[1] if budget[1] >= 0 else cfg.budget_amount}")
    lines.append(f'BUDGET_TIER = "{budget[0]}"')
    lines.append("")

    lines.append("# Providers (auto-detected from environment)")
    lines.append("PROVIDERS = {")
    for name, env, _, _ in PROVIDERS:
        lines.append(f'    "{name.lower()}": os.environ.get("{env}", ""),')
    lines.append("}")
    lines.append("ACTIVE_PROVIDERS = {k: v for k, v in PROVIDERS.items() if v}")
    lines.append("")

    if "model-router-ai" in cap_names:
        lines.append("# Model Router")
        lines.append("try:")
        lines.append("    from personal_agent.router import create_free_router")
        lines.append(f"    router = create_free_router(max_monthly={budget[1] if budget[1] >= 0 else cfg.budget_amount})")
        lines.append("except Exception:")
        lines.append("    router = None")
        lines.append("")

    if "resilience-ai" in cap_names:
        lines.append("# Resilience")
        lines.append("try:")
        lines.append("    from resilience_ai import RetryConfig, CircuitBreaker")
        lines.append("    RETRY = RetryConfig(max_retries=3, backoff_base=2.0)")
        lines.append("    CIRCUIT = CircuitBreaker(failure_threshold=5, recovery_timeout=60)")
        lines.append("except ImportError:")
        lines.append("    RETRY = CIRCUIT = None")
        lines.append("")

    if "structured-output-ai" in cap_names:
        lines.append("# Structured Output")
        lines.append("try:")
        lines.append("    from structured_output_ai import StructuredOutput")
        lines.append("except ImportError:")
        lines.append("    StructuredOutput = None")
        lines.append("")

    if "consensus-ai" in cap_names:
        lines.append("# Consensus")
        lines.append("try:")
        lines.append("    from consensus_ai import MajorityVote, WeightedConsensus")
        lines.append("    CONSENSUS = MajorityVote(min_votes=3)")
        lines.append("except ImportError:")
        lines.append("    CONSENSUS = None")
        lines.append("")

    if "evaluation-ai" in cap_names:
        lines.append("# Evaluation")
        lines.append("try:")
        lines.append("    from evaluation_ai import EvaluationHarness, AdversarialPanel")
        lines.append("    EVALUATOR = EvaluationHarness(adversarial=True)")
        lines.append("except ImportError:")
        lines.append("    EVALUATOR = None")
        lines.append("")

    if "observability-ai" in cap_names:
        lines.append("# Observability")
        lines.append("try:")
        lines.append("    from observability_ai import configure_logging, CostTracker")
        lines.append("    configure_logging(level='INFO', json_output=True)")
        lines.append("    COSTS = CostTracker()")
        lines.append("except ImportError:")
        lines.append("    COSTS = None")
        lines.append("")

    if "security-ai" in cap_names:
        lines.append("# Security")
        lines.append("try:")
        lines.append("    from security_ai import validate_config, mask_secrets, AuditLogger")
        lines.append("    AUDIT = AuditLogger()")
        lines.append("except ImportError:")
        lines.append("    AUDIT = None")
        lines.append("")

    if "rag-ai" in cap_names:
        lines.append("# RAG")
        lines.append("try:")
        lines.append("    from rag_ai import DocumentStore, HybridSearch")
        lines.append("    DOCS = DocumentStore()")
        lines.append("except ImportError:")
        lines.append("    DOCS = None")
        lines.append("")

    if "genetic-optimizer-ai" in cap_names:
        lines.append("# Genetic Optimizer")
        lines.append("try:")
        lines.append("    from genetic_optimizer_ai import GeneticOptimizer, TaskClassifier")
        lines.append("    OPTIMIZER = GeneticOptimizer()")
        lines.append("    CLASSIFIER = TaskClassifier()")
        lines.append("except ImportError:")
        lines.append("    OPTIMIZER = CLASSIFIER = None")
        lines.append("")

    return "\n".join(lines) + "\n"


def _pip_extras(cap_names):
    extras = []
    if any(c in cap_names for c in ["consensus-ai", "evaluation-ai", "observability-ai",
                                     "security-ai", "rag-ai", "genetic-optimizer-ai"]):
        extras.append("all")
    if not extras:
        return ""
    return f'[{",".join(extras)}]'


# --- Build & Install ---

def build_screen(win, cfg):
    win.erase()
    h, w = win.getmaxyx()
    y = draw_header(win, 0, "Building Configuration")
    y += 1
    step = 0
    total_steps = 4 + len(cfg.agents)

    def log(msg, kind="info"):
        nonlocal y
        if y < h - 3:
            draw_status(win, y, msg, kind)
            y += 1
            win.refresh()

    def advance():
        nonlocal step
        step += 1
        if y < h - 3:
            draw_progress(win, h - 3, step, total_steps)
            win.refresh()

    repo = Path(cfg.repo_dir).resolve()
    caps = [CAPABILITIES[i] for i in cfg.capabilities]
    cap_names = [c[0] for c in caps]

    log("Installing personal-agent...", "warning")
    install_extras = _pip_extras(cap_names)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             f"git+{PA_REPO}{install_extras}"],
            capture_output=True, text=True, timeout=120,
        )
        log("personal-agent installed", "success")
    except Exception as e:
        log(f"pip install failed: {e}", "error")
    advance()

    for idx in cfg.agents:
        name, agent_dir, _ = AGENTS[idx]
        log(f"Generating {name} config...", "info")

        if agent_dir == "claude-code":
            content = generate_claude_md(cfg)
            dst = repo / "CLAUDE.md"
            dst.write_text(content)
            log("  + CLAUDE.md (generated)", "success")

            skills = repo / ".claude" / "skills"
            skills.mkdir(parents=True, exist_ok=True)
            _write_skills(skills, cap_names)
            log("  + .claude/skills/", "success")

        elif agent_dir == "cursor":
            content = generate_cursorrules(cfg)
            dst = repo / ".cursorrules"
            dst.write_text(content)
            log("  + .cursorrules (generated)", "success")

        elif agent_dir == "opencode":
            content = generate_agents_md(cfg)
            dst = repo / "AGENTS.md"
            dst.write_text(content)
            log("  + AGENTS.md (generated)", "success")

        advance()

    log("Generating ai_config.py...", "info")
    config_content = generate_ai_config(cfg)
    config_dst = repo / "ai_config.py"
    config_dst.write_text(config_content)
    log("  + ai_config.py (generated)", "success")
    advance()

    log("Writing build manifest...", "info")
    manifest = {
        "agents": [AGENTS[i][1] for i in cfg.agents],
        "capabilities": cap_names,
        "budget": BUDGET_TIERS[cfg.budget_tier][0],
        "budget_amount": cfg.budget_amount,
        "theme": cfg.theme_name,
        "providers": {name: bool(os.environ.get(env)) for name, env, _, _ in PROVIDERS},
    }
    manifest_dst = repo / ".pa-config.json"
    manifest_dst.write_text(json.dumps(manifest, indent=2) + "\n")
    log("  + .pa-config.json", "success")
    advance()

    y += 1
    log("Build complete!", "success")
    y += 1
    if y < h - 1:
        win.addstr(y, 2, "Press any key to continue...",
                   curses.color_pair(theme.colors.accent))
    win.refresh()
    win.getch()


def _write_skills(skills_dir, cap_names):
    review_skill = textwrap.dedent("""\
        ---
        name: pa-review
        description: Run personal-agent review on current changes
        ---

        Run personal-agent in investigation mode to review current changes:

        ```bash
        pa --investigate "Review staged changes for correctness, security, and style" --repo .
        ```

        Report findings with severity levels. Do not auto-commit.
    """)
    (skills_dir / "pa-review.md").write_text(review_skill)

    fix_skill = textwrap.dedent("""\
        ---
        name: pa-fix
        description: Worker/arbiter loop to fix an issue
        ---

        Run personal-agent to fix the specified issue:

        ```bash
        pa "$ARGUMENTS" --repo . -c "pytest tests/"
        ```

        The worker will propose changes, the arbiter reviews them,
        and the loop continues until the arbiter accepts.
    """)
    (skills_dir / "pa-fix.md").write_text(fix_skill)

    if "consensus-ai" in cap_names:
        consensus_skill = textwrap.dedent("""\
            ---
            name: pa-consensus
            description: Multi-model consensus vote on a decision
            ---

            Use personal-agent with consensus-ai for multi-model voting:

            ```bash
            pa --investigate "$ARGUMENTS" --repo . --consensus
            ```

            Returns majority vote across multiple LLM providers.
        """)
        (skills_dir / "pa-consensus.md").write_text(consensus_skill)


def summary_screen(win, cfg):
    win.erase()
    h, w = win.getmaxyx()
    y = draw_header(win, 0, "Setup Complete")
    y += 1

    caps = [CAPABILITIES[i] for i in cfg.capabilities]
    cap_names = [c[0] for c in caps]
    budget = BUDGET_TIERS[cfg.budget_tier]

    win.addstr(y, 2, "Agents:", curses.A_BOLD)
    y += 1
    for idx in cfg.agents:
        if y >= h - 14:
            break
        name, _, _ = AGENTS[idx]
        win.addstr(y, 4, f"+ {name}", curses.color_pair(theme.colors.success))
        y += 1

    y += 1
    if y < h - 12:
        win.addstr(y, 2, "AI Stack:", curses.A_BOLD)
        y += 1
        for name, _, _ in caps:
            if y >= h - 10:
                break
            win.addstr(y, 4, f"+ {name}", curses.color_pair(theme.colors.success))
            y += 1

    y += 1
    if y < h - 8:
        win.addstr(y, 2, f"Budget: {budget[0]}",
                   curses.color_pair(theme.colors.primary) | curses.A_BOLD)
        y += 1
        win.addstr(y, 2, f"Project: {cfg.repo_dir}",
                   curses.color_pair(theme.colors.foreground))
        y += 2

    if y < h - 4:
        win.addstr(y, 2, "Generated files:",
                   curses.color_pair(theme.colors.primary) | curses.A_BOLD)
        y += 1
        files = ["ai_config.py", ".pa-config.json"]
        for idx in cfg.agents:
            _, agent_dir, _ = AGENTS[idx]
            if agent_dir == "claude-code":
                files.extend(["CLAUDE.md", ".claude/skills/"])
            elif agent_dir == "cursor":
                files.append(".cursorrules")
            elif agent_dir == "opencode":
                files.append("AGENTS.md")
        for f in files:
            if y >= h - 2:
                break
            win.addstr(y, 4, f, curses.color_pair(theme.colors.info))
            y += 1

    y += 1
    if y < h - 1:
        win.addstr(y, 2, "Press q to exit",
                   curses.color_pair(theme.colors.accent))

    win.refresh()
    while True:
        if win.getch() in (ord("q"), ord("Q"), 27):
            break


# --- Main ---

def main(stdscr):
    global theme
    cfg = BuildConfig(theme_name=initial_theme)

    load_theme(cfg.theme_name)
    theme.apply(stdscr)
    curses.curs_set(0)
    stdscr.keypad(True)

    # Welcome
    stdscr.erase()
    y = draw_header(stdscr, 0, "personal-agent builder")
    y += 1
    stdscr.addstr(y, 2, "Build AI coding-agent configs using FlossWare libraries",
                  curses.color_pair(theme.colors.foreground))
    y += 1
    stdscr.addstr(y, 2, "github.com/sfloess/personal-agent",
                  curses.color_pair(theme.colors.info))
    y += 1
    stdscr.addstr(y, 2, f"Theme: {cfg.theme_name}  (press 't' to change, Enter to start)",
                  curses.color_pair(theme.colors.accent))
    stdscr.refresh()

    key = stdscr.getch()
    if key == ord("t"):
        picked = theme_picker(stdscr)
        if picked:
            cfg.theme_name = picked
            load_theme(cfg.theme_name)
            theme.apply(stdscr)

    # Step 1: Agents
    agents = checkbox_menu(stdscr, "1/5  Select Coding Agents", AGENTS)
    if agents is None:
        return
    if not agents:
        stdscr.erase()
        draw_status(stdscr, 0, "No agents selected. Exiting.", "warning")
        stdscr.refresh()
        curses.napms(1500)
        return
    cfg.agents = agents

    # Step 2: Capabilities
    cap_items = [(name, key, desc) for name, desc, default in CAPABILITIES]
    cap_defaults = {i for i, (_, _, default) in enumerate(CAPABILITIES) if default}
    caps = checkbox_menu(stdscr, "2/5  FlossWare AI Capabilities", cap_items,
                         preselected=cap_defaults)
    if caps is None:
        return
    cfg.capabilities = caps

    # Step 3: Budget
    budget_idx = radio_menu(stdscr, "3/5  Monthly Budget", BUDGET_TIERS)
    if budget_idx is None:
        return
    cfg.budget_tier = budget_idx
    cfg.budget_amount = float(BUDGET_TIERS[budget_idx][1])
    if BUDGET_TIERS[budget_idx][1] == -1:
        custom = text_input(stdscr, "Monthly budget in USD:", "25")
        try:
            cfg.budget_amount = float(custom)
        except ValueError:
            cfg.budget_amount = 25.0

    # Step 4: Project dir
    cfg.repo_dir = text_input(stdscr, "Project directory:", os.getcwd())
    repo_path = Path(cfg.repo_dir).resolve()
    cfg.repo_dir = str(repo_path)

    if not (repo_path / ".git").exists():
        stdscr.erase()
        draw_status(stdscr, 0, f"Not a git repo: {repo_path}", "error")
        stdscr.addstr(1, 2, "Press any key to exit.",
                      curses.color_pair(theme.colors.accent))
        stdscr.refresh()
        stdscr.getch()
        return

    # Step 5: API keys
    api_key_screen(stdscr, cfg)

    # Build
    build_screen(stdscr, cfg)

    # Summary
    summary_screen(stdscr, cfg)


# --- CLI ---

initial_theme = "dark"
for i, arg in enumerate(sys.argv[1:], 1):
    if arg == "--theme" and i + 1 < len(sys.argv):
        initial_theme = sys.argv[i + 1]
    elif arg.startswith("--theme="):
        initial_theme = arg.split("=", 1)[1]
    elif arg in ("--help", "-h"):
        print("Usage: python3 scripts/setup.py [--theme dark|borland-3d|dos|...]")
        print()
        print("Interactive TUI builder for personal-agent configurations.")
        print("Selects agents, FlossWare AI capabilities, budget, and generates configs.")
        print()
        print("Available themes: dark, light, default, borland-3d, dos,")
        print("                  dbase-iii, dbase-iv, dbase-iv-3d, ti-99-4a, trs-80")
        print()
        print("Non-interactive? Use: scripts/install.sh --agent all --repo /path")
        sys.exit(0)

if __name__ == "__main__":
    if not sys.stdout.isatty():
        print("Non-interactive environment. Use scripts/install.sh instead.")
        sys.exit(1)

    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
