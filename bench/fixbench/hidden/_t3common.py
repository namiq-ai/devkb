"""Shared checks for the cross-file change tasks (T3): AST over every tracked Python file of the work tree."""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def files():
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    out += subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "*.py"], cwd=ROOT, capture_output=True,
                          text=True).stdout.split()
    return [ROOT / f for f in sorted(set(out)) if not Path(f).name.startswith("test_hidden_") and (ROOT / f).exists()]


def count_defs(name: str) -> int:
    return sum(len(re.findall(rf"^\s*(?:async\s+)?def {name}\b", p.read_text(errors="replace"), re.M)) for p in files())


def module_aliases(tree: ast.AST, module: str) -> tuple[set[str], dict[str, str]]:
    """Names bound to `devkb.<module>` (import devkb.x as y / from devkb import x / from . import x) and names imported
    from it (from devkb.x import a as b -> {b: a})."""
    mods, names = set(), {}
    short = module.rsplit(".", 1)[-1]
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.endswith(module) or a.name == "devkb." + module:
                    mods.add(a.asname or a.name)
        elif isinstance(n, ast.ImportFrom):
            m = n.module or ""
            if m.endswith(module) or m.endswith("." + short) or m == short:
                for a in n.names:
                    names[a.asname or a.name] = a.name
            elif m in ("devkb", "devkb.extractors", "") or m.endswith("extractors"):
                for a in n.names:
                    if a.name == short:
                        mods.add(a.asname or a.name)
    return mods, names
