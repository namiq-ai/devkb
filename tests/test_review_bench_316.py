"""#316: the two-way review harness's pure parts: findings, verification, defect groups, the tracked row, the gate input and the report section."""
import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "bench" / "review"))
sys.path.insert(0, str(HERE / "bench" / "policy"))
rb = importlib.import_module("reviewbench")
rt = importlib.import_module("release_table")
gate = importlib.import_module("gate")

REPLY = """Some prose.
```json
[{"file": "a.py", "line": 10, "severity": "high", "claim": "c1", "repro": "exit 1", "evidence": "e"},
 {"file": "b.py", "line": "7", "severity": "low", "claim": "c2", "repro": "", "evidence": ""},
 {"file": "c.py", "line": 3, "severity": "critical", "claim": "bad severity"},
 {"line": 4, "severity": "low"}]
```"""


def test_findings_are_read_from_the_last_json_block_and_bad_ones_dropped():
    fs = rb.parse_findings(REPLY)
    assert [(f["file"], f["line"], f["severity"]) for f in fs] == [("a.py", 10, "high"), ("b.py", 7, "low")]
    assert rb.parse_findings("no block") == [] and rb.parse_findings("```json\nnot json\n```") == []


def test_a_reproduction_counts_only_when_it_exits_1_on_two_clean_checkouts(monkeypatch):
    monkeypatch.setattr(rb, "tree", lambda commit, dest: None)
    f = {"file": "a.py", "line": 1, "severity": "high", "claim": "c", "repro": "x"}
    facts = {"head": "h"}
    assert rb.verify_finding(f, facts, run=lambda cmd, w: 1)["reproduced"] is True
    assert rb.verify_finding(f, facts, run=lambda cmd, w: 0)["reproduced"] is False
    flaky = iter([1, 0])
    assert rb.verify_finding(f, facts, run=lambda cmd, w: next(flaky))["reproduced"] is False, "once is not reproduced"
    assert rb.verify_finding({**f, "repro": ""}, facts)["reproduced"] is False
    none = rb.verify_finding(f, facts, run=lambda cmd, w: None)
    assert none["reproduced"] is False and "sandbox" in none["why"], none


def test_an_unsandboxed_machine_runs_nothing(monkeypatch):
    monkeypatch.setattr(rb.shutil, "which", lambda n: None)
    assert rb.sandbox("touch /tmp/should-not-exist-316", Path("/tmp")) is None


def test_a_reproduction_really_runs_in_the_sandbox_when_there_is_one(tmp_path):
    import shutil
    if not shutil.which("bwrap"):
        return
    assert rb.sandbox("exit 1", tmp_path) == 1 and rb.sandbox("exit 0", tmp_path) == 0
    (tmp_path / "data").write_text("x")
    assert rb.sandbox("test -f data && exit 1; exit 0", tmp_path) == 1
    assert rb.sandbox("curl -s -m 3 https://example.com >/dev/null 2>&1; exit 1", tmp_path) == 1     # no network: the command fails, not the sandbox


def _f(file, line, sev, ok=True):
    return {"file": file, "line": line, "severity": sev, "reproduced": ok, "claim": "", "repro": "r", "evidence": ""}


def test_defect_groups_only_one_arm_found():
    per = {"nodevkb": [_f("a.py", 10, "high"), _f("a.py", 14, "low"), _f("b.py", 5, "medium"), _f("z.py", 1, "low", ok=False)],
           "devkb": [_f("a.py", 12, "high"), _f("c.py", 9, "medium")]}
    assert rb.groups(per) == {"nodevkb": 1, "devkb": 1}, rb.groups(per)    # a.py is shared (10, 12 and 14 are one group); b.py only nodevkb; c.py only devkb


def test_the_tracked_row_has_every_field_the_ticket_names():
    per = {"nodevkb": [_f("a.py", 10, "high"), _f("b.py", 5, "low", ok=False)], "devkb": [_f("a.py", 10, "high")]}
    runs = [{"cost": 0.5, "model_calls": 20, "ctx_tokens": 300000, "out_tokens": 6000, "seconds": 240, "devkb_nav": 0, "guardrail_fired": 0}]
    r = rb.arm_row(270, "nodevkb", runs, per)
    for k in ("pr", "arm", "findings", "reproduced", "by_severity", "only_this_arm", "cost", "model_calls", "ctx_tokens", "out_tokens", "seconds",
              "devkb_queries", "hook_decisions"):
        assert k in r, k
    assert r["findings"] == 2 and r["reproduced"] == 1 and r["by_severity"] == {"high": 1, "medium": 0, "low": 0} and r["only_this_arm"] == 0


def test_the_gate_input_merges_the_arms_and_takes_the_stricter_severity():
    per = {"nodevkb": [_f("a.py", 10, "medium")], "devkb": [_f("a.py", 11, "high"), _f("b.py", 3, "low")]}
    out = rb.gate_input(per)
    assert len(out) == 2 and out[0]["severity"] == "high" and out[0]["arms"] == {"nodevkb": "medium", "devkb": "high"} and out[0]["open"] is True


def test_the_gate_reads_what_the_harness_writes():
    pr = {"author": gate.OWNER, "is_fork": False, "files": ["devkb/a.py"], "ci_green": True, "suite_green": True, "hidden_check": True, "head": "h"}
    open_high = [{"severity": "high", "open": True, "arms": {"devkb": "high"}}]
    d = gate.decide(pr, open_high, gate.OWNER, "host", ("host",))
    assert d["action"] == "rework", d


def test_the_release_report_has_a_review_section():
    rows = [{"pr": 270, "arm": a, "reviews": 1, "findings": 4, "reproduced": 3, "by_severity": {"high": 1, "medium": 1, "low": 1}, "only_this_arm": 1,
             "cost": 0.5, "model_calls": 20, "ctx_tokens": 300000, "out_tokens": 6000, "seconds": 240, "devkb_queries": 2, "hook_decisions": 3}
            for a in ("nodevkb", "devkb")]
    out = "\n".join(rt.review_section(rows))
    assert "| nodevkb | 1 | 4 | 3 (1 / 1 / 1) | 1 | 0.50 | 20 | 300 | 4.0 | 2.0 | 3.0 |" in out and "#270" in out, out
    assert "No pull request was reviewed" in "\n".join(rt.review_section([]))


def test_the_prompt_demands_a_self_contained_reproduction():
    assert "SELF-CONTAINED" in rb.PROMPT and "/tmp/x.py" in rb.PROMPT
