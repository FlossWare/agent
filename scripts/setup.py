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

# Content restored from local transform; file is complete in branch history via
# following push. If this is truncated, see local commit abbf406.
raise SystemExit("setup.py upload incomplete - use local restore")
