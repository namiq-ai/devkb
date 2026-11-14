"""ODSF-310 workflow benchmark: the truth is computed from source, so the truth itself is tested."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_BENCH = Path(__file__).resolve().parents[1] / "devkb" / "bench"
sys.path.insert(0, str(_BENCH))

import workflow_run  # noqa: E402
import workflow_tasks  # noqa: E402


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def test_a_library_method_with_the_same_name_is_not_a_caller(tmp_path):
    root = _repo(tmp_path, {
        "pkg/ctx.py": "def resolve(code):\n    return code\n",
        "pkg/use.py": "from pkg.ctx import resolve\n\ndef a():\n    return resolve('x')\n",
        "pkg/mod.py": "from pkg import ctx\n\ndef b():\n    return ctx.resolve('y')\n",
        "pkg/paths.py": "from pathlib import Path\n\ndef c():\n    return Path('.').resolve()\n",
        "tests/test_ctx.py": "from pkg.ctx import resolve\n\ndef test_r():\n    assert resolve('z')\n",
    })
    s = workflow_tasks.scan(root)
    got = {workflow_tasks.short(k) for k in workflow_tasks.callers_of(s, "resolve")}
    assert got == {"pkg/use.py::a", "pkg/mod.py::b", "tests/test_ctx.py::test_r"}, "Path.resolve() is not a call to pkg.ctx.resolve"


def test_a_name_no_library_shares_is_matched_by_name(tmp_path):
    root = _repo(tmp_path, {"a.py": "def parse_front_matter(t):\n    raise ValueError('front matter must be a mapping')\n",
                            "b.py": "import a as m\n\ndef use(x):\n    return x.parse_front_matter(1)\n"})
    s = workflow_tasks.scan(root)
    assert [workflow_tasks.short(k) for k in workflow_tasks.callers_of(s, "parse_front_matter")] == ["b.py::use"]
    assert s["raises"] == [(("a.py", "parse_front_matter"), "front matter must be a mapping")]


def test_scores_reward_the_right_sets_and_nothing_else():
    rca = {"kind": "rca", "truth": {"raiser": "a.py::f", "callers": ["b.py::g", "t/test_a.py::test_f"], "test_files": ["t/test_a.py"]}}
    right = json.dumps({"raiser": "a.py::f", "callers": ["b.py::g", "t/test_a.py::test_f"], "test_files": ["t/test_a.py"]})
    assert workflow_run.score(rca, right)["score"] == 1.0
    assert workflow_run.score(rca, json.dumps({"raiser": "b.py::g", "callers": [], "test_files": []}))["score"] == 0.0
    onb = {"kind": "onboard", "truth": {"top5": ["a.py::x", "a.py::y", "a.py::z", "a.py::w", "a.py::v"]}}
    assert workflow_run.score(onb, '{"top": ["a.py::x", "a.py::q", "a.py::v"]}')["score"] == 0.667
