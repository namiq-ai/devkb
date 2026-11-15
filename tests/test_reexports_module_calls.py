"""Calls through a package re-export, and calls made outside any function, in the graph, the packs and the benchmark
truth. Found on lnbits (`from lnbits.core.crud import get_wallet`, re-exported by `crud/__init__.py`: 22 of 39 caller
files were missing from both) and Mealie (`app_dirs = get_app_dirs()` at import time)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from devkb import build_symbols, process_api
from devkb.packs import Packer
from devkb.project_context import ProjectContext

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "devkb" / "bench"))
import module_truth as mt  # noqa: E402

FILES = {
    "app/__init__.py": "",
    "app/crud/__init__.py": "from .wallets import get_wallet\n\n__all__ = ['get_wallet']\n",
    "app/crud/wallets.py": "def get_wallet(wallet_id):\n    return wallet_id\n",
    "app/direct.py": "from app.crud.wallets import get_wallet\n\n\ndef a():\n    return get_wallet(1)\n",
    "app/via_package.py": "from app.crud import get_wallet\n\n\ndef b():\n    return get_wallet(2)\n",
    "app/via_module.py": "from app import crud\n\n\ndef c():\n    return crud.get_wallet(3)\n",
    "app/at_import.py": "from app.crud import get_wallet\n\nDEFAULT = get_wallet(0)\n\n\nclass Holder:\n    value = get_wallet(9)\n",
    "app/lazy.py": "from app.crud import get_wallet\n\nLATER = lambda: get_wallet(4)\n",
    "tests/test_wallets.py": "from app.crud import get_wallet\n\n\ndef test_get():\n    assert get_wallet(5) == 5\n",
}
REAL = {"app/direct.py", "app/via_package.py", "app/via_module.py", "app/at_import.py", "tests/test_wallets.py"}


def _repo(tmp_path: Path) -> Path:
    for rel, text in FILES.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True)
    return tmp_path


def _api(root: Path, monkeypatch) -> process_api.ProcessAPI:
    g = build_symbols.extract(root)
    store = root / ".devkb"
    store.mkdir()
    d = g.to_dict()
    (store / "nodes.jsonl").write_text("\n".join(json.dumps(n) for n in d["nodes"]) + "\n")
    (store / "edges.jsonl").write_text("\n".join(json.dumps(e) for e in d["edges"]) + "\n")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    (store / "manifest.json").write_text(json.dumps({"built_at": "2026-11-15T00:00:00+00:00", "git_head": head}))
    ctx = ProjectContext(code="TST", repo_root=root, ticket_prefix="TST", issues_dir=root / "issues", tests_dir=root / "tests",
                         sprint_dir=root / "h", devkb_dir=store, board_file=root / "b.md", wp_map_file=root / "w.json")
    monkeypatch.setattr(process_api, "resolve", lambda code: ctx)
    return process_api.ProcessAPI("TST", telemetry=False)


def test_graph_follows_reexports_and_records_import_time_callers(tmp_path):
    g = build_symbols.extract(_repo(tmp_path))
    target = "app/crud/wallets.py::get_wallet"
    callers = {e.src.split("::")[0] for e in g.edges("CALLS") if e.dst == target}
    assert callers == REAL - {"app/at_import.py"}
    node = next(n for n in g.nodes("Symbol") if n.natural_key == target)
    assert node.props["module_callers"] == ["app/at_import.py"], "the lambda's call runs later, inside a function"


def test_refactor_pack_lists_every_caller_file(tmp_path, monkeypatch):
    pack = Packer(_api(_repo(tmp_path), monkeypatch)).refactor("get_wallet", path="app/crud/wallets.py")
    listed = {line.split("`")[1] for line in pack.split("## Files with a direct caller")[1].split("##")[0].splitlines()
              if line.startswith("- `")}
    assert listed == REAL
    assert "app/at_import.py` — called at module level" in pack


def test_callers_tool_reports_import_time_files(tmp_path, monkeypatch):
    r = _api(_repo(tmp_path), monkeypatch).call("callers", symbol="app/crud/wallets.py::get_wallet")
    assert r["module_level_files"] == ["app/at_import.py"]


def test_truth_follows_reexports_and_counts_import_time_callers(tmp_path):
    t = mt.Truth(_repo(tmp_path))
    files = {c[0] for c in t.callers()[("app/crud/wallets.py", "get_wallet")]}
    assert files == REAL
    prod, tests, clean = t.up(("app/crud/wallets.py", "get_wallet"))
    assert "<module>" not in {k[1] for k in prod}, "an import-time call is not a function on a chain"
    assert {k[0] for k in tests} == {"tests/test_wallets.py"}


def test_coverage_says_when_more_files_hold_unattributed_calls(tmp_path, monkeypatch):
    api = _api(_repo(tmp_path), monkeypatch)
    i, _ = api._resolve("app/crud/wallets.py::get_wallet")
    api.idx.props[i]["unresolved_calls"] = 30
    api.idx.props[i]["unresolved_files"] = [f"app/m{n}.py" for n in range(20)]
    api.idx.props[i]["unresolved_file_count"] = 22
    text = Packer(api).coverage([i], set())
    assert "They are in 22 files; the 10 with the most" in text and "Search the whole repository" in text
    assert "Search only these files" not in text


def test_coverage_points_at_listed_files_when_no_other_file_holds_unattributed_calls(tmp_path, monkeypatch):
    api = _api(_repo(tmp_path), monkeypatch)
    i, _ = api._resolve("app/crud/wallets.py::get_wallet")
    api.idx.props[i]["unresolved_calls"] = 1
    api.idx.props[i]["unresolved_files"] = ["app/direct.py"]
    text = Packer(api).coverage([i], {"app/direct.py"})
    assert "already listed above" in text and "files not recorded" not in text


def test_pack_without_a_graph_says_how_to_build_one(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    monkeypatch.setattr(sys, "argv", ["packs", "--project", str(root), "refactor", "get_wallet"])
    from devkb import packs
    assert packs.main() == 2
    assert "run `devkb build --project" in capsys.readouterr().err


def test_calls_through_a_dotted_module_path(tmp_path):
    files = {"pkg/__init__.py": "", "pkg/context.py": "def get_run_context():\n    return 1\n",
             "pkg/user.py": "import pkg.context\n\n\ndef run():\n    return pkg.context.get_run_context()\n",
             "pkg/other.py": "def run(request):\n    return request.app.get_run_context()\n"}
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True)
    g = build_symbols.extract(tmp_path)
    callers = {e.src for e in g.edges("CALLS") if e.dst == "pkg/context.py::get_run_context"}
    assert callers == {"pkg/user.py::run"}, "a chain through an object (`request.app`) is not attributed"
    t = mt.Truth(tmp_path)
    assert t.callers()[("pkg/context.py", "get_run_context")] == {("pkg/user.py", "run")}
