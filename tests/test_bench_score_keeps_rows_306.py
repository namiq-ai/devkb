"""#306: re-scoring one arm (POLICY_ARMS) replaces only that arm's rows; without the filter everything is rescored as before."""
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "policy"))
pb = importlib.import_module("policybench")


def _row(arm, rep, tag, issue="9"):
    return {"run": f"p{issue}-{arm}-r{rep}", "issue": issue, "arm": arm, "rep": str(rep), "acceptance": {"pass": True}, "suite_pass": True,
            "cost": 0.1, "devkb_queries": 0, "guardrail_fired": 0, "dogfood_log": [], "tag": tag}


def _setup(tmp_path, monkeypatch, issue="9", arms=("none", "main")):
    monkeypatch.setattr(pb, "B", tmp_path)
    for arm in arms:
        for rep in (1, 2):
            d = tmp_path / "runs" / f"p{issue}-{arm}-r{rep}"
            d.mkdir(parents=True)
            (d / "end").write_text(json.dumps({"exit": 0, "seconds": 1}))
    monkeypatch.setattr(pb, "score_run", lambda i, out: _row(out.name.split("-")[1], out.name.split("-")[2][1:], "new", i))
    old = [_row(a, r, "old", issue) for a in arms for r in (1, 2)]
    (tmp_path / f"results-{issue}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in old))
    (tmp_path / "results-policy.jsonl").write_text("".join(json.dumps(r) + "\n" for r in old))


def _tags(path):
    return sorted((r["arm"], r["tag"]) for r in (json.loads(l) for l in path.read_text().splitlines() if l.strip()))


def test_scoring_one_arm_keeps_the_other_arms_rows_in_both_files(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("POLICY_ARMS", "main")
    pb.score(["9"])
    want = [("main", "new"), ("main", "new"), ("none", "old"), ("none", "old")]
    assert _tags(tmp_path / "results-9.jsonl") == want and _tags(tmp_path / "results-policy.jsonl") == want


def test_scoring_every_arm_rescores_everything_as_before(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.delenv("POLICY_ARMS", raising=False)
    pb.score(["9"])
    assert _tags(tmp_path / "results-9.jsonl") == [("main", "new")] * 2 + [("none", "new")] * 2


def test_a_filtered_scoring_of_one_ticket_does_not_touch_another_tickets_file(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    other = tmp_path / "results-8.jsonl"
    other.write_text(json.dumps(_row("none", 1, "old", "8")) + "\n")
    monkeypatch.setenv("POLICY_ARMS", "main")
    pb.score(["9"])
    assert _tags(other) == [("none", "old")]
