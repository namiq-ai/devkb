"""#340: the agents' checkouts are outside the harness repository, and a change to that repository during a run is flagged."""
import importlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "bench" / "policy"))
pb = importlib.import_module("policybench")
sb = importlib.import_module("storybench")
rt = importlib.import_module("release_table")


def _repo(tmp_path):
    r = tmp_path / "harness"
    (r / "bench" / "policy").mkdir(parents=True)
    (r / "bench" / "policy" / "policybench.py").write_text("x = 1\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(r), *c], check=True, capture_output=True)
    return r


def test_the_default_work_and_template_directories_are_outside_the_repository(monkeypatch):
    monkeypatch.delenv("POLICY_WORK_DIR", raising=False)
    w = pb.work_dir().resolve()
    assert pb.HARNESS_REPO not in w.parents and w != pb.HARNESS_REPO
    assert pb.HARNESS_REPO not in Path(str(Path.home() / ".cache" / "devkb" / "policy-templates")).resolve().parents
    monkeypatch.setenv("POLICY_WORK_DIR", "/somewhere/else")
    assert pb.work_dir() == Path("/somewhere/else")


def test_harness_state_sees_a_changed_tracked_file_and_a_new_file_but_not_the_harness_own_outputs(tmp_path):
    r = _repo(tmp_path)
    clean = pb.harness_state(r)
    (r / "bench" / "policy" / "results-9.jsonl").write_text("{}\n")           # the harness's own output
    (r / "bench" / "policy" / "no-mcp.json").write_text("{}\n")
    assert pb.harness_state(r) == clean
    (r / "bench" / "policy" / "policybench.py").write_text("x = 2\n")        # an agent's stray edit
    assert pb.harness_state(r) != clean
    (r / "bench" / "policy" / "policybench.py").write_text("x = 1\n")
    (r / "tests").mkdir()
    (r / "tests" / "test_stray.py").write_text("")                            # an agent's stray new file
    assert "test_stray.py" in pb.harness_state(r)


def _run(tmp_path, monkeypatch, repo, writes):
    monkeypatch.setattr(pb, "B", tmp_path)
    monkeypatch.setattr(pb, "HARNESS_REPO", repo)
    monkeypatch.setattr(pb, "template_for", lambda a, issue=None: tmp_path / "t")
    monkeypatch.setattr(pb, "from_template", lambda t, w: (Path(w).mkdir(parents=True), (Path(w) / ".bench-arm.json").write_text("{}")))
    monkeypatch.setattr(pb.toolenv, "build", lambda ref: {"bin": str(tmp_path / "devkb"), "commit": "x", "hook_sha": "x"})
    monkeypatch.setattr(pb, "score_run", lambda *a, **k: None)
    real = subprocess.run
    real_sh = sb.sh
    monkeypatch.setattr(sb, "sh", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps({"title": "T", "body": "b"}), "") if cmd[:2] == ["gh", "issue"] else real_sh(cmd, **kw))

    def run(cmd, *a, **k):
        if cmd and cmd[0] == "claude":
            if writes:
                (repo / "bench" / "policy" / "policybench.py").write_text("x = 'changed by an agent'\n")
            return subprocess.CompletedProcess(cmd, 0)
        return real(cmd, *a, **k)
    monkeypatch.setattr(pb.subprocess, "run", run)
    msg = pb._run_one("9", "main", 1)
    return msg, json.loads((tmp_path / "runs" / "p9-main-r1" / "end").read_text())


def test_a_run_that_changes_the_harness_repository_is_flagged(tmp_path, monkeypatch):
    msg, end = _run(tmp_path, monkeypatch, _repo(tmp_path), writes=True)
    assert "CONTAMINATED" in msg and any("policybench.py" in x for x in end["contaminated"])


def test_a_clean_run_has_no_contamination_key(tmp_path, monkeypatch):
    msg, end = _run(tmp_path, monkeypatch, _repo(tmp_path), writes=False)
    assert "CONTAMINATED" not in msg and "contaminated" not in end


def _row(arm, run, cost, contaminated=()):
    return {"run": run, "issue": "9", "arm": arm, "rep": "1", "turns": 3, "calls": {}, "ctx_tokens": 1, "cost": cost, "seconds": 60,
            "suite_pass": True, "devkb_nav": 0, "devkb_selftest": 0, "acceptance": {"pass": True}, "contaminated": list(contaminated)}


def test_the_table_leaves_contaminated_runs_out_of_the_means_and_names_them(monkeypatch):
    monkeypatch.setattr(rt, "guard_rows", lambda s: [])
    rows = [_row("main", "p9-main-r1", 1.0), _row("main", "p9-main-r2", 9.0, ["?? x"])]
    out = rt.table([("9", rows)])
    assert "| 1.00 (1.00–1.00) |" in out or "1.00 (1.00–1.00)" in out
    assert "WARNING #9: 1 run(s) changed the harness repository" in out and "p9-main-r2" in out
