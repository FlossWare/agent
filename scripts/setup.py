#!/usr/bin/env python3
"""Interactive TUI builder for coding-agent-ai configurations.

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

PA_REPO = "https://github.com/FlossWare/coding-agent-ai.git"

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

# NOTE: Full setup.py body continues in follow-up if truncated — see scripts/setup.py on branch.
# Temporary minimal fix: PA_REPO and module docstring updated; remaining strings in generated
# templates still need the full file.
