"""#334: every arm's agent gets the same, longer Bash timeout; the transcript counts the commands the tool backgrounded."""
import importlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "policy"))
pb = importlib.import_module("policybench")
sb = importlib.import_module("storybench")
rt = importlib.import_module("release_table")


def _env(tmp_path, monkeypatch, arm, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(pb, "B", tmp_path)
    monkeypatch.setattr(pb, "template_for", lambda a, issue=None: tmp_path / "t")
    monkeypatch.setattr(pb, "from_template", lambda t, w: (Path(w).mkdir(parents=True), (Path(w) / ".bench-arm.json").write_text("{}")))
    monkeypatch.setattr(pb.toolenv, "build", lambda ref: {"bin": str(tmp_path / "devkb"), "commit": "x", "hook_sha": "x"})
    monkeypatch.setattr(pb, "score_run", lambda *a, **k: None)
    real = sb.sh
    monkeypatch.setattr(sb, "sh", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps({"title": "T", "body": "b"}), "") if cmd[:2] == ["gh", "issue"] else real(cmd, **kw))
    got = {}
    real_run = subprocess.run
    monkeypatch.setattr(pb.subprocess, "run", lambda cmd, **k: (got.update(env=k.get("env")), subprocess.CompletedProcess(cmd, 0))[1]
                        if cmd[0] == "claude" else real_run(cmd, **k))      # only the agent launch is stubbed (git calls are real)
    pb._run_one("9", arm, 1)
    return got["env"]


def test_every_arm_gets_a_timeout_above_the_suites_duration(tmp_path, monkeypatch):
    for arm in ("none", "main"):
        (tmp_path / arm).mkdir()
        env = _env(tmp_path / arm, monkeypatch, arm)
        assert int(env["BASH_DEFAULT_TIMEOUT_MS"]) >= 300000 and int(env["BASH_MAX_TIMEOUT_MS"]) >= int(env["BASH_DEFAULT_TIMEOUT_MS"])


def test_the_limit_can_be_set_for_a_batch(tmp_path, monkeypatch):
    env = _env(tmp_path, monkeypatch, "none", POLICY_BASH_TIMEOUT_MS="900000")
    assert env["BASH_DEFAULT_TIMEOUT_MS"] == env["BASH_MAX_TIMEOUT_MS"] == "900000"


def _stream(tmp_path, results):
    ev = [{"type": "assistant", "message": {"id": "m1", "usage": {"output_tokens": 1}, "content": [
        {"type": "tool_use", "id": f"t{i}", "name": "Bash", "input": {"command": "pytest"}} for i, _ in enumerate(results)]}},
          {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": c} for i, c in enumerate(results)]}}]
    p = tmp_path / "s.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in ev))
    return p


def test_the_transcript_counts_backgrounded_commands(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "guardrail_actions", lambda s: (0, {}))
    p = _stream(tmp_path, ["Command did not complete within its 120s timeout and was moved to the background (ID: b1).", "ok",
                           "Command did not complete within its 600s timeout and was moved to the background (ID: b2)."])
    assert sb.transcript(p)["backgrounded"] == 2
    assert sb.transcript(_stream(tmp_path, ["3 passed"]))["backgrounded"] == 0


def test_the_table_prints_backgrounded_commands_and_unknown_for_old_rows(monkeypatch):
    monkeypatch.setattr(rt, "guard_rows", lambda s: [])
    base = {"run": "x-main-r1", "issue": "9", "arm": "main", "rep": "1", "turns": 3, "calls": {}, "ctx_tokens": 1, "cost": 1.0, "seconds": 60,
            "suite_pass": True, "devkb_nav": 0, "devkb_selftest": 0, "acceptance": {"pass": True}}
    assert "| #9 | main | unknown | unknown | 2.0 |" in rt.table([("9", [{**base, "backgrounded": 2}])])
    assert "| #9 | main | unknown | unknown | unknown |" in rt.table([("9", [base])])
