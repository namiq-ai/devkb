from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _t3common import ROOT, count_defs  # noqa: E402


def test_the_method_is_renamed_and_the_other_edges_are_not():
    t = ast.parse((ROOT / "devkb" / "model.py").read_text())
    cls = next(n for n in ast.walk(t) if isinstance(n, ast.ClassDef) and n.name == "DevKBGraph")
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    assert "edges_by_verb" in methods and "edges" not in methods
    assert count_defs("edges") == 2, "the two other functions named edges keep their name"


def test_the_graph_still_works_through_the_new_name():
    sys.path.insert(0, str(ROOT))
    from devkb.model import DevKBGraph
    g = DevKBGraph()
    assert hasattr(g, "edges_by_verb") and not hasattr(DevKBGraph, "edges")
