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


def test_no_label_when_no_match_has_the_query_spelling(tmp_path):
    r = _repo(tmp_path, {"pkg/a.py": "def Parse_Thing():\n    return 1\n"}).resolve("parse_thing")
    assert [m["how"] for m in r["matches"]] == ["exact"]


def test_case_never_lifts_a_test_symbol_above_production(tmp_path):
    rt = _repo(tmp_path, {"app/core.py": "def parse(s):\n    return s\n",
                          "tests/test_core.py": "def Parse():\n    return 1\n\ndef test_it():\n    assert Parse() == 1\n"})
    r = rt.resolve("Parse")
    assert [m["k"] for m in r["matches"]] == ["app/core.py::parse", "tests/test_core.py::Parse"]
