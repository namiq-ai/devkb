from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _t3common import ROOT, count_defs, files, module_aliases  # noqa: E402


def test_the_helper_is_renamed_and_no_other_run_is():
    src = (ROOT / "devkb" / "extractors" / "tickets_git.py").read_text()
    assert "def _git(" in src and "def _run(" not in src
    assert count_defs("_run") == 3


def test_no_module_still_uses_the_old_name():
    bad = []
    for p in files():
        t = ast.parse(p.read_text(errors="replace"))
        mods, names = module_aliases(t, "tickets_git")
        if any(v == "_run" for v in names.values()):
            bad.append(f"{p.relative_to(ROOT)}: imports _run from tickets_git")
        for n in ast.walk(t):
            if isinstance(n, ast.Attribute) and n.attr == "_run" and isinstance(n.value, ast.Name) and n.value.id in mods:
                bad.append(f"{p.relative_to(ROOT)}:{n.lineno}")
    assert not bad, bad
