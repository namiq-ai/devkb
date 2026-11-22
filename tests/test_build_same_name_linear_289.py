"""#289: build work stays proportional to unresolved calls plus definitions when many symbols share a name. Counted calls, not seconds, so
it cannot flake on a loaded machine (#377)."""
from __future__ import annotations

import subprocess

from devkb import build_symbols


def _repo(root, files):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    for c in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@e.x", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True, capture_output=True)
    return root


def test_many_same_named_definitions_and_callers_do_not_multiply(tmp_path, monkeypatch):
    n = 300
    files = {f"f{i}.py": "def run():\n    return 1\n" for i in range(n)}
    files["u.py"] = "".join(f"def u{i}():\n    return run()\n" for i in range(n))
    calls = [0]
    real = build_symbols._could_reach

    def counted(*a, **k):
        calls[0] += 1
        return real(*a, **k)

    monkeypatch.setattr(build_symbols, "_could_reach", counted)
    build_symbols.extract(_repo(tmp_path, files))
    assert calls[0] <= 50 * n, f"{calls[0]} reach tests for {n} definitions and {n} callers (n*n = {n * n})"


def test_unresolved_calls_are_still_counted_per_symbol_through_the_groups(tmp_path):
    files = {"a.py": "class A:\n    def run(self):\n        return 1\n", "b.py": "class B:\n    def run(self):\n        return 2\n",
             "u.py": "def go(x):\n    return x.run()\n\n\ndef go2(y):\n    return y.run()\n"}
    g = build_symbols.extract(_repo(tmp_path, files))
    props = {n.natural_key: n.props for n in g.nodes("Symbol")}
    for key in ("a.py::A.run", "b.py::B.run"):
        assert props[key].get("unresolved_calls") == 2, (key, props[key])      # both callers could be either class's method
        assert props[key].get("unresolved_files") == ["u.py"]
