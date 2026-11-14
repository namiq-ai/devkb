"""Tiny git helpers shared across devkb/build.py and devkb/build_symbols.py --
split out specifically to avoid a circular import between them (build.py
needs build_symbols.load_cache(), build_symbols.py needs this)."""
from __future__ import annotations

import subprocess
from pathlib import Path


def git_head(repo_root: Path) -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                            cwd=str(repo_root), timeout=10)
        return r.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"
