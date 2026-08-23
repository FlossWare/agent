# Fleet Multi-Review (FMR) Pattern

The FMR pattern sends code to multiple free LLM providers concurrently,
synthesizes an arbiter verdict, fixes findings, then runs a meta-review
loop until all issues are resolved.

## Architecture

```
                    ┌───────────────────────────────────────┐
                    │            Arbiter (Claude)            │
                    │  Synthesizes verdicts from all workers │
                    └───────────┬───────────────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
     ┌────────▼───────┐ ┌──────▼────────┐ ┌──────▼────────┐
     │   Worker 1     │ │   Worker 2    │ │   Worker 3    │
     │   Gemini       │ │  OpenRouter   │ │  Cerebras/    │
     │   (native)     │ │  (gemma-3)    │ │  fallback     │
     └────────────────┘ └───────────────┘ └───────────────┘
```

## How It Works

### Round 1: Initial Review

1. **Fan out** — Send code to 3+ free API workers in parallel
2. **Collect** — Each worker returns findings with severity (HIGH/MEDIUM/LOW)
3. **Synthesize** — Arbiter merges findings, deduplicates, assigns final verdicts
4. **Fix** — Address all HIGH and MEDIUM findings
5. **Meta-review** — Send fixed code back through workers for approval

### Round N: Fix-Review Loop

Repeat until all workers return `APPROVE`:

```
Fix findings ──▶ Re-submit to workers ──▶ Synthesize
     ▲                                        │
     └────── REQUEST_CHANGES ◀────────────────┘
```

## API Providers (Free Tier)

| Provider | Model | Access |
|----------|-------|--------|
| Google Gemini | gemini-2.5-flash | Native API (`$GOOGLE_API_KEY`) |
| OpenRouter | gemma-3-27b-it:free | OpenAI-compatible (`$OPENROUTER_API_KEY`) |
| OpenRouter | deepseek-r1-0528:free | Fallback model |
| OpenRouter | nemotron-super-49b:free | Fallback model |

## Worker Prompt Template

Each worker receives:

```
REVIEW these files for:
1) Bugs (logic errors, crashes, edge cases)
2) API misuse (curses-themes, shell conventions)
3) Security issues (injection, credential leaks)
4) Error handling (masked errors, missing cleanup)

Return JSON: {
  "verdict": "APPROVE" | "REQUEST_CHANGES",
  "findings": [{
    "severity": "HIGH" | "MEDIUM" | "LOW",
    "file": "filename",
    "issue": "description"
  }]
}

[file contents follow]
```

## Arbiter Synthesis

The arbiter (Claude) receives all worker verdicts and:

1. **Deduplicates** findings that overlap across workers
2. **Promotes** severity when multiple workers flag the same issue
3. **Demotes** findings that only one worker flagged as LOW
4. **Final verdict**: `REQUEST_CHANGES` if any HIGH/MEDIUM remains, else `APPROVE`

## Example Session

```
FMR Round 1
├── Worker 1 (Gemini):     REQUEST_CHANGES  3 findings
├── Worker 2 (OpenRouter):  REQUEST_CHANGES  5 findings
├── Worker 3 (fallback):    REQUEST_CHANGES  4 findings
└── Arbiter synthesis:      REQUEST_CHANGES  6 unique findings
    ├── HIGH: --theme arg IndexError (2 workers agreed)
    ├── HIGH: pip error masking (3 workers agreed)
    ├── MEDIUM: TMPDIR shadowing (1 worker)
    └── 3 more...

[fixes applied]

FMR Round 2 (meta-review)
├── Worker (Gemini):        REQUEST_CHANGES  2 findings
└── Fixes applied

FMR Round 3 (meta-review)
├── Worker (Gemini):        APPROVE  0 findings
└── Done
```

## Integration with setup.py / install.sh

The FMR pattern was used to review these scripts:

| File | Lines | Findings Fixed |
|------|-------|---------------|
| `scripts/setup.py` | 1030 | pip timeout, theme arg parsing |
| `scripts/install.sh` | 170 | TMPDIR shadowing, error masking, .git check |

## Usage in Your Projects

To run FMR on your own code:

```bash
# 1. Set API keys
export GOOGLE_API_KEY=your-gemini-key
export OPENROUTER_API_KEY=your-openrouter-key

# 2. Send to workers (example with Gemini)
curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=$GOOGLE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"contents":[{"parts":[{"text":"REVIEW: [your code]"}]}]}'

# 3. Send to workers (example with OpenRouter)
curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"google/gemma-3-27b-it:free","messages":[{"role":"user","content":"REVIEW: [your code]"}]}'

# 4. Synthesize verdicts, fix, repeat
```

## Cost

All providers used are free tier. Total cost per FMR pass: **$0.00**.
