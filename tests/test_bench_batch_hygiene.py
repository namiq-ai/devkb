"""Batch hygiene: one batch can hold several tickets each at its own base; a finished run is never silently skipped; moving a run to
runs-archive/ is not contamination."""
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
pb = importlib.import_module("policybench")
rt = importlib.import_module("release_table")


def test_a_ticket_has_its_own_base_in_a_shared_batch(monkeypatch):
    monkeypatch.setenv("POLICY_MAIN", "MAINSHA")
    monkeypatch.setenv("POLICY_BASES", "118=aaa111,120=bbb222")
    monkeypatch.setitem(pb.BASES, "rmain", "MAINSHA")
    monkeypatch.setitem(pb.BASES, "release", "v0.2.11")
    assert pb.base_for("rmain", "118") == "aaa111" and pb.base_for("rmain", "120") == "bbb222"
    assert pb.base_for("rmain", "203") == "MAINSHA"                      # no entry: the batch's main
    assert pb.base_for("rmain") == "MAINSHA"                              # no ticket: unchanged
    assert pb.base_for("release", "118") == "v0.2.11"                    # an arm that does not follow main keeps its own ref
    monkeypatch.delenv("POLICY_BASES")
    assert pb.base_for("rmain", "118") == "MAINSHA"


def test_a_finished_run_is_refused_not_skipped_and_resume_lists_it(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(pb, "B", tmp_path)
    for tag, end in (("p118-rmainhid-r1", {"exit": 0}), ("p118-rmainhid-r2", {"exit": "error"}), ("p118-ctxhid-r1", {"exit": "base-red"})):
        d = tmp_path / "runs" / tag
        d.mkdir(parents=True)
        (d / "end").write_text(json.dumps(end))
    jobs = [("118", a, r) for a in ("rmainhid", "ctxhid") for r in (1, 2)]
    with pytest.raises(SystemExit, match="p118-rmainhid-r1"):
        pb.check_collisions(jobs, resume=False)                          # r1 finished; r2 errored and r1 of ctxhid was red: set up again
    assert pb.check_collisions(jobs, resume=True) == ["p118-rmainhid-r1"]
    assert "keeping 1 finished runs: p118-rmainhid-r1" in capsys.readouterr().out
    assert pb.check_collisions([("118", "ctxhid", 2)], resume=False) == []


def test_a_row_flagged_only_for_runs_archive_is_not_contaminated():
    row = {"contaminated": ["?? bench/policy/runs-archive/pre-ctx-batch/p118-rmainhid-r1/score.json"]}
    assert rt.contaminated(row) == []
    both = {"contaminated": [row["contaminated"][0], " M devkb/x.py"]}
    assert rt.contaminated(both) == [" M devkb/x.py"]
    assert rt.contaminated({}) == []


def test_the_harness_state_ignores_the_archive(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "bench" / "policy" / "runs-archive").mkdir(parents=True)
    before = pb.harness_state(tmp_path)
    (tmp_path / "bench" / "policy" / "runs-archive" / "x.json").write_text("{}")
    assert pb.harness_state(tmp_path) == before
    (tmp_path / "bench" / "policy" / "stray.txt").write_text("x")
    assert pb.harness_state(tmp_path) != before
