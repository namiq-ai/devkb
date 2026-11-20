"""#372: `symbol NAME` lists the match spelled as the query first and labels matches in another case; case alone never
lifts test code above production code."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devkb import process_api, read_tools  # noqa: E402


def _repo(root: Path, files: dict) -> read_tools.ReadTools:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True, capture_output=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True,
                   capture_output=True)
    return read_tools.ReadTools(process_api.ProcessAPI(str(root), telemetry=False))


CASE = {"pkg/tools.py": "def trace(text):\n    return text\n\ndef use():\n    return trace('x')\n\ndef use2():\n    return trace('y')\n",
        "pkg/settings.py": "TRACE = ('a', 'b')\n"}


def test_the_query_spelling_comes_first_and_the_other_case_is_labelled(tmp_path):
    rt = _repo(tmp_path, CASE)
    r = rt.resolve("TRACE")
    assert r["how"] == "exact"
    assert [m["k"] for m in r["matches"]] == ["pkg/settings.py::TRACE", "pkg/tools.py::trace"]   # 0 callers, but the spelling
    assert [m["how"] for m in r["matches"]] == ["exact", "exact (other case)"]
    text = read_tools.render_symbol(r)
    assert "how exact (other case)" in text and text.index("pkg/settings.py") < text.index("pkg/tools.py")


def test_the_lowercase_query_puts_the_function_first(tmp_path):
    r = _repo(tmp_path, CASE).resolve("trace")
    assert [m["k"] for m in r["matches"]] == ["pkg/tools.py::trace", "pkg/settings.py::TRACE"]
    assert r["matches"][1]["how"] == "exact (other case)"


def test_every_match_spelled_otherwise_is_labelled_even_when_none_has_the_query_spelling(tmp_path):
    rt = _repo(tmp_path, {"pkg/tools.py": "def trace(t):\n    return t\n\nclass Trace:\n    pass\n"})
    assert [m["how"] for m in rt.resolve("TRACE")["matches"]] == ["exact (other case)", "exact (other case)"]
    assert {m["k"]: m["how"] for m in rt.resolve("Trace")["matches"]} == {"pkg/tools.py::Trace": "exact",
                                                                          "pkg/tools.py::trace": "exact (other case)"}


def test_case_never_lifts_a_test_symbol_above_production(tmp_path):
    rt = _repo(tmp_path, {"app/core.py": "def parse(s):\n    return s\n",
                          "tests/test_core.py": "def Parse():\n    return 1\n\ndef test_it():\n    assert Parse() == 1\n"})
    r = rt.resolve("Parse")
    assert [(m["k"], m["how"]) for m in r["matches"]] == [("app/core.py::parse", "exact (other case)"),
                                                          ("tests/test_core.py::Parse", "exact")]


def test_qualified_regex_and_glob_queries_put_the_spelling_first_and_label_the_rest(tmp_path):
    rt = _repo(tmp_path, {"pkg/a.py": "def trace(t):\n    return t\n\ndef use():\n    return trace(1)\n\nTRACE = 1\n"})
    for q, how in (("a.TRACE", "module"), ("pkg.a.TRACE", "module"), ("re:^TRACE$", "regex"), ("TRAC*", "glob")):
        r = rt.resolve(q)
        assert r["how"] == how, q
        assert [(m["k"], m["how"]) for m in r["matches"]] == [("pkg/a.py::TRACE", how), ("pkg/a.py::trace", f"{how} (other case)")], q


def test_a_suffix_query_keeps_the_case_of_every_typed_part(tmp_path):
    rt = _repo(tmp_path, {"pkg/a.py": "class Store:\n    def add(self):\n        return 1\n\nclass store:\n    def add(self):\n        return 2\n\n"
                                      "def f():\n    return store().add() + store().add()\n"})
    r = rt.resolve("Store.add")
    assert [(m["k"], m["how"]) for m in r["matches"]] == [("pkg/a.py::Store.add", "qualified"), ("pkg/a.py::store.add", "qualified (other case)")]


def test_the_spelling_goes_before_the_depth_of_the_qualified_name(tmp_path):
    rt = _repo(tmp_path, {"pkg/a.py": "def run():\n    return 1\n\ndef go():\n    return run()\n\nclass Task:\n    def Run(self):\n        return 2\n"})
    r = rt.resolve("Run")
    assert [(m["k"], m["how"]) for m in r["matches"]] == [("pkg/a.py::Task.Run", "exact"), ("pkg/a.py::run", "exact (other case)")]
