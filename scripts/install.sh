#!/usr/bin/env bash
# Install personal-agent and configure it for your coding agent.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/sfloess/personal-agent/main/scripts/install.sh | bash
#   # or
#   ./scripts/install.sh [--agent claude|cursor|opencode|all] [--repo /path/to/project]
#
# What it does:
#   1. Installs personal-agent via pip
#   2. Copies integration files for your chosen agent into your project
#   3. Verifies API keys are set

set -euo pipefail

AGENT="all"
REPO_DIR="."
PA_REPO="https://github.com/sfloess/personal-agent.git"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --agent|-a) AGENT="$2"; shift 2 ;;
        --repo|-r)  REPO_DIR="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: install.sh [--agent claude|cursor|opencode|all] [--repo /path/to/project]"
            echo ""
            echo "Options:"
            echo "  --agent, -a   Agent to configure (claude, cursor, opencode, all). Default: all"
            echo "  --repo, -r    Project directory to install into. Default: current directory"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

REPO_DIR="$(cd "$REPO_DIR" && pwd)"

if [[ ! -d "$REPO_DIR/.git" ]]; then
    echo "ERROR: $REPO_DIR is not a git repository."
    exit 1
fi

echo "=== personal-agent installer ==="
echo "Agent:   $AGENT"
echo "Project: $REPO_DIR"
echo ""

# Step 1: Install personal-agent
echo "[1/3] Installing personal-agent..."
PIP_CMD=""
if command -v pip &>/dev/null; then
    PIP_CMD="pip"
elif command -v pip3 &>/dev/null; then
    PIP_CMD="pip3"
else
    echo "ERROR: pip not found. Install Python 3.11+ first."
    exit 1
fi

if ! $PIP_CMD install --quiet "git+${PA_REPO}" 2>&1; then
    echo "ERROR: pip install failed. Check Python 3.11+ and network connectivity."
    exit 1
fi

if command -v pa &>/dev/null; then
    echo "  pa CLI installed: $(which pa)"
else
    echo "  WARNING: pa not found in PATH. You may need to add ~/.local/bin to PATH."
fi

# Step 2: Copy integration files
echo "[2/3] Setting up agent integration..."

PA_TMPDIR="$(mktemp -d)"
trap 'rm -rf "$PA_TMPDIR"' EXIT
git clone --depth 1 --quiet "$PA_REPO" "$PA_TMPDIR/pa" || {
    echo "ERROR: Could not clone $PA_REPO"
    exit 1
}

copy_no_clobber() {
    local src="$1" dst="$2"
    if [[ ! -e "$dst" ]]; then
        cp "$src" "$dst" && return 0
    fi
    return 1
}

copy_integration() {
    local agent="$1"
    local src="$PA_TMPDIR/pa/integrations/$agent"

    if [[ ! -d "$src" ]]; then
        echo "  WARNING: No integration found for '$agent'"
        return
    fi

    case "$agent" in
        claude-code)
            mkdir -p "$REPO_DIR/.claude/skills"
            copy_no_clobber "$src/CLAUDE.md" "$REPO_DIR/CLAUDE.md" && echo "  Created CLAUDE.md" || echo "  CLAUDE.md already exists (skipped)"
            for skill in "$src/skills/"*.md; do
                name="$(basename "$skill")"
                copy_no_clobber "$skill" "$REPO_DIR/.claude/skills/$name" && echo "  Created .claude/skills/$name" || echo "  .claude/skills/$name exists (skipped)"
            done
            if [[ -f "$src/hooks/pre-commit" ]]; then
                mkdir -p "$REPO_DIR/.git/hooks"
                copy_no_clobber "$src/hooks/pre-commit" "$REPO_DIR/.git/hooks/pre-commit" && chmod +x "$REPO_DIR/.git/hooks/pre-commit" && echo "  Installed pre-commit hook" || echo "  pre-commit hook exists (skipped)"
            fi
            ;;
        cursor)
            copy_no_clobber "$src/.cursorrules" "$REPO_DIR/.cursorrules" && echo "  Created .cursorrules" || echo "  .cursorrules already exists (skipped)"
            ;;
        opencode)
            copy_no_clobber "$src/AGENTS.md" "$REPO_DIR/AGENTS.md" && echo "  Created AGENTS.md" || echo "  AGENTS.md already exists (skipped)"
            if [[ -f "$src/.opencode.yaml" ]]; then
                copy_no_clobber "$src/.opencode.yaml" "$REPO_DIR/.opencode.yaml" && echo "  Created .opencode.yaml" || echo "  .opencode.yaml exists (skipped)"
            fi
            ;;
    esac
}

case "$AGENT" in
    claude)   copy_integration "claude-code" ;;
    cursor)   copy_integration "cursor" ;;
    opencode) copy_integration "opencode" ;;
    all)
        copy_integration "claude-code"
        copy_integration "cursor"
        copy_integration "opencode"
        ;;
    *)
        echo "ERROR: Unknown agent '$AGENT'. Use: claude, cursor, opencode, or all"
        exit 1
        ;;
esac

# Step 3: Check API keys
echo "[3/3] Checking API keys..."

FOUND=0
for var in GROQ_API_KEY CEREBRAS_API_KEY OPENROUTER_API_KEY GEMINI_API_KEY COHERE_API_KEY HUGGINGFACE_API_KEY; do
    if [[ -n "${!var:-}" ]]; then
        echo "  $var: set"
        FOUND=$((FOUND + 1))
    fi
done

if [[ $FOUND -eq 0 ]]; then
    echo ""
    echo "  WARNING: No API keys found. Set at least one:"
    echo "    export COHERE_API_KEY=your-key      # recommended"
    echo "    export GROQ_API_KEY=your-key"
    echo "    export OPENROUTER_API_KEY=your-key"
    echo ""
    echo "  Get free keys at:"
    echo "    Cohere:     https://dashboard.cohere.com/api-keys"
    echo "    Groq:       https://console.groq.com/keys"
    echo "    OpenRouter:  https://openrouter.ai/keys"
else
    echo "  $FOUND API key(s) configured"
fi

echo ""
echo "=== Done! ==="
echo ""
echo "Quick start:"
echo "  pa \"Fix the bug in auth.py\" --repo $REPO_DIR -c \"pytest tests/\""
echo "  pa --investigate \"What does this codebase do?\" --repo $REPO_DIR"
