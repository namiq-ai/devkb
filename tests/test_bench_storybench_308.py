"""#308: a storybench row carries what a policybench row does: the check's hash, the failed and flaky test ids, the green-base record."""
import importlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "bench" / "policy"))
sb = importlib.import_module("storybench")
pb = importlib.import_module("policybench")

NEEDED = ("accept_sha256", "suite_failed", "suite_flaky", "base_green", "base_suite", "tests_collected", "issue")


def _python(w):
    """w/.venv/bin/python that runs this interpreter with its packages (a bare symlink would lose the venv's site-packages)."""
    (w / ".venv" / "bin").mkdir(parents=True)
    py = w / ".venv" / "bin" / "python"
    py.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    py.chmod(0o755)


def _git(cwd, *a):
    return subprocess.run(["git", "-c", "user.email=t@e.x", "-c", "user.name=T", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _checkout(tmp_path, with_arm_json=True):
    B = tmp_path / "bench"
    w = B / "work" / "7-devkb-r1"
    _python(w)
    (w / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    _git(w, "init", "-q")
    _git(w, "add", "-A")
    _git(w, "commit", "-qm", "base")
    (w / ".bench-base").write_text(_git(w, "rev-parse", "HEAD").strip())
    if with_arm_json:
        (w / ".bench-arm.json").write_text(json.dumps({"base_green": True, "base_suite": "1 passed", "tests_collected": 1}))
    out = B / "runs" / "7-devkb-r1"
    out.mkdir(parents=True)
    (out / "end").write_text(json.dumps({"exit": 0, "seconds": 5}))
    (out / "stream.jsonl").write_text("")
    (B / "accept").mkdir()
    (B / "accept" / "7.py").write_text('import json\nprint(json.dumps({"pass": True}))\n')
    return B


def test_a_storybench_row_carries_the_policybench_fields(monkeypatch, tmp_path):
    B = _checkout(tmp_path)
    monkeypatch.setattr(sb, "B", B)
    monkeypatch.setattr(pb, "B", B)
    sb.score("7")
    row = json.loads((B / "results-7.jsonl").read_text().splitlines()[0])
    for k in NEEDED:
        assert k in row, (k, sorted(row))
    assert row["base_green"] is True and row["tests_collected"] == 1 and len(row["accept_sha256"]) == 64
    assert row["suite_pass"] is True and row["suite_failed"] == [] and row["suite_flaky"] == []


def test_a_flaky_test_is_recorded_not_held_against_the_run(monkeypatch, tmp_path):
    B = _checkout(tmp_path)
    w = B / "work" / "7-devkb-r1"
    (w / "test_flaky.py").write_text("import pathlib\n\n\ndef test_flaky():\n    p = pathlib.Path(__file__).with_name('once')\n"
                                     "    first = not p.exists()\n    p.write_text('x')\n    assert not first\n")
    monkeypatch.setattr(sb, "B", B)
    monkeypatch.setattr(pb, "B", B)
    sb.score("7")
    row = json.loads((B / "results-7.jsonl").read_text().splitlines()[0])
    assert row["suite_pass"] is True and any("test_flaky" in x for x in row["suite_flaky"]), row["suite_flaky"]


def test_record_base_writes_the_green_base_record(tmp_path):
    w = tmp_path / "w"
    _python(w)
    (w / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    meta = sb.record_base(w)
    assert meta["base_green"] is True and meta["tests_collected"] == 1
    assert json.loads((w / ".bench-arm.json").read_text()) == meta
