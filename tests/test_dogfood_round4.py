"""Limitations of devkb found by using it on its own code during C# round 4 (#40, docs/specs/csharp-4-dogfood-log.md)."""
from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

from devkb import build_symbols, process_api, read_tools
from devkb.packs import Packer
from devkb.project_context import ProjectContext

SRC = '''
class _Index:
    def extension(self, name):
        return name

    def member(self, n):
        if n:
            return self.member(n - 1)
        return 0


def calls_in(index: _Index, x):
    index.extension(x)
    index.extension(x)
    return index.extension(x)


def static_call():
    return _Index.extension(None, 1)
'''


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True)
    return tmp_path


def _pairs(g) -> set[tuple[str, str]]:
    key = {n.uid: n.natural_key for n in g.nodes("Symbol")}
    return {(key.get(e.from_uid), key.get(e.to_uid)) for e in g.edges("CALLS")}


def _api(root: Path, monkeypatch):
    g = build_symbols.extract(root)
    store = root / ".devkb"
    store.mkdir()
    d = g.to_dict()
    (store / "nodes.jsonl").write_text("\n".join(json.dumps(n) for n in d["nodes"]) + "\n")
    (store / "edges.jsonl").write_text("\n".join(json.dumps(e) for e in d["edges"]) + "\n")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    (store / "manifest.json").write_text(json.dumps({"built_at": "2026-11-17T00:00:00+00:00", "git_head": head}))
    ctx = ProjectContext(code="DF", repo_root=root, ticket_prefix="DF", issues_dir=root / "issues", tests_dir=root / "tests",
                         sprint_dir=root / "h", devkb_dir=store, board_file=root / "b.md", wp_map_file=root / "w.json")
    monkeypatch.setattr(process_api, "resolve", lambda code: ctx)
    return process_api.ProcessAPI("DF", telemetry=False)


def test_d1_a_private_class_types_an_annotated_parameter_and_a_static_call(tmp_path):
    pairs = _pairs(build_symbols.extract(_repo(tmp_path, {"m.py": SRC})))
    assert ("m.py::calls_in", "m.py::_Index.extension") in pairs
    assert ("m.py::static_call", "m.py::_Index.extension") in pairs
    assert build_symbols._class_ref(ast.parse("_Index", mode="eval").body) == "_Index"
    assert build_symbols._class_ref(ast.parse("index", mode="eval").body) is None


def test_d3_a_recursive_call_is_proved_by_the_call_not_the_def(tmp_path, monkeypatch):
    packer = Packer(_api(_repo(tmp_path, {"m.py": SRC}), monkeypatch))
    member = next(i for i, k in enumerate(packer.idx.keys) if k == "m.py::_Index.member")
    site = packer.call_site(member, "member")
    assert site.startswith("m.py:8:") and "self.member(n - 1)" in site


def test_d2_the_incomplete_line_counts_functions_not_call_sites():
    text = (Path(__file__).resolve().parents[1] / "devkb" / "packs.py").read_text()
    assert "function(s) could not be" in text and "call site(s) under this name" not in text


def test_d4_uses_skips_data_files(tmp_path, monkeypatch):
    root = _repo(tmp_path, {"a.py": "def needle():\n    return 1\n", "runs/t.jsonl": '{"x": "needle"}\n' * 5})
    out = json.dumps(read_tools.ReadTools(_api(root, monkeypatch)).uses("needle"))
    assert "t.jsonl" not in out and "a.py" in out
