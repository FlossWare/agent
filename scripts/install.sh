#!/usr/bin/env bash
# Install coding-agent-ai and configure it for your coding agent.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/FlossWare/coding-agent-ai/main/scripts/install.sh | bash
#   # or
#   ./scripts/install.sh [--agent claude|cursor|opencode|all] [--repo /path/to/project]
#
# What it does:
#   1. Installs coding-agent-ai via pip
#   2. Copies agent integration files into the target repo
#   3. Checks for API keys and prints setup guidance

set -euo pipefail

PA_REPO="https://github.com/FlossWare/coding-agent-ai.git"
AGENT="all"
REPO_DIR="$(pwd)"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --agent) AGENT="$2"; shift 2 ;;
        --repo)  REPO_DIR="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "=== coding-agent-ai installer ==="
echo "Agent target: $AGENT"
echo "Project dir:  $REPO_DIR"
echo ""

# Step 1: Install coding-agent-ai
echo "[1/3] Installing coding-agent-ai..."
if command -v pip3 &>/dev/null; then
    pip3 install --user "git+${PA_REPO}" || pip3 install "git+${PA_REPO}"
elif command -v pip &>/dev/null; then
    pip install --user "git+${PA_REPO}" || pip install "git+${PA_REPO}"
else
    echo "ERROR: pip not found. Install Python 3 and pip first."
    exit 1
fi
echo "  Installed."

# Locate this repo's integrations/ (when run from a clone) or download them
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
INTEGRATIONS=""
if [[ -d "$SCRIPT_DIR/../integrations" ]]; then
    INTEGRATIONS="$SCRIPT_DIR/../integrations"
elif [[ -d "$REPO_DIR/integrations" ]]; then
    INTEGRATIONS="$REPO_DIR/integrations"
fi

copy_no_clobber() {
    local src="$1" dest="$2"
    if [[ -e "$dest" ]]; then
        return 1
    fi
    cp "$src" "$dest"
    return 0
}

copy_integration() {
    local name="$1"
    local src="$INTEGRATIONS/$name"
    if [[ -z "$INTEGRATIONS" || ! -d "$src" ]]; then
        echo "  Skipping $name (integrations not available in this context)"
        return
    fi
    echo "[2/3] Configuring $name..."
    case "$name" in
        claude-code)
            mkdir -p "$REPO_DIR/.claude/skills"
            for skill in pa-fix.md pa-investigate.md pa-review.md; do
                copy_no_clobber "$src/skills/$skill" "$REPO_DIR/.claude/skills/$skill" && echo "  Created .claude/skills/$skill" || echo "  .claude/skills/$skill exists (skipped)"
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
