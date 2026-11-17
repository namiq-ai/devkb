from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _t3common import ROOT, count_defs, files, module_aliases  # noqa: E402


def test_the_function_is_renamed_and_no_other_extract_is():
    src = (ROOT / "devkb" / "build_symbols.py").read_text()
    assert "def extract_symbols(" in src and "\ndef extract(" not in src
    assert count_defs("extract") == 20, "the other 20 functions named extract keep their name"


def test_no_reference_to_the_old_name_remains():
    bad = []
    for p in files():
        t = ast.parse(p.read_text(errors="replace"))
        mods, names = module_aliases(t, "build_symbols")
        if names.get("extract") == "extract" or any(v == "extract" for v in names.values()):
            bad.append(f"{p.relative_to(ROOT)}: imports extract from build_symbols")
        for n in ast.walk(t):
            if isinstance(n, ast.Attribute) and n.attr == "extract" and isinstance(n.value, ast.Name) and n.value.id in mods:
                bad.append(f"{p.relative_to(ROOT)}:{n.lineno}: {n.value.id}.extract")
        if p.name == "build_symbols.py":
            for n in ast.walk(t):
                if isinstance(n, ast.Name) and n.id == "extract":
                    bad.append(f"build_symbols.py:{n.lineno}: bare extract")
    assert not bad, bad
