"""#330: a run's stream records what the hook said to the agent, and the transcript and table report it."""
import importlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "policy"))
pb = importlib.import_module("policybench")
sb = importlib.import_module("storybench")
rt = importlib.import_module("release_table")


def test_the_agent_launch_asks_for_hook_events(tmp_path, monkeypatch):
    monkeypatch.setattr(pb, "B", tmp_path)
    monkeypatch.setattr(pb, "template_for", lambda a, issue=None: tmp_path / "t")
    monkeypatch.setattr(pb, "from_template", lambda t, w: (Path(w).mkdir(parents=True), (Path(w) / ".bench-arm.json").write_text("{}")))
    monkeypatch.setattr(pb.toolenv, "build", lambda ref: {"bin": str(tmp_path / "devkb"), "commit": "x", "hook_sha": "x"})
    monkeypatch.setattr(pb, "score_run", lambda *a, **k: None)
    real, real_sh = subprocess.run, sb.sh
    monkeypatch.setattr(sb, "sh", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps({"title": "T", "body": "b"}), "") if cmd[:2] == ["gh", "issue"] else real_sh(cmd, **kw))
    got = {}
    monkeypatch.setattr(pb.subprocess, "run", lambda cmd, **k: (got.update(cmd=cmd), subprocess.CompletedProcess(cmd, 0))[1] if cmd[0] == "claude" else real(cmd, **k))
    pb._run_one("9", "main", 1)
    assert "--include-hook-events" in got["cmd"]


def _hook(i, text, event="PreToolUse"):
    return {"type": "system", "subtype": "hook_response", "hook_id": f"h{i}", "hook_event": event, "exit_code": 0,
            "output": json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}) if text is not None else ""}


def _asst(i):
    return {"type": "assistant", "message": {"id": f"m{i}", "usage": {"output_tokens": 1}, "content": []}}


def _t(tmp_path, monkeypatch, events):
    monkeypatch.setattr(sb, "guardrail_actions", lambda s: (0, {}))
    p = tmp_path / "s.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in events))
    return sb.transcript(p)


def test_the_transcript_counts_hook_outputs_and_keeps_the_first_text(tmp_path, monkeypatch):
    t = _t(tmp_path, monkeypatch, [_hook(1, "REMINDER one"), _asst(1), _hook(2, "second answer"), _asst(2)])
    assert t["hook_outputs"] == 2 and t["hook_first_output"] == "REMINDER one"     # the text, not the JSON wrapper


def test_a_hook_that_said_nothing_is_not_an_output(tmp_path, monkeypatch):
    t = _t(tmp_path, monkeypatch, [_hook(1, None), _hook(2, "only this"), _asst(1)])
    assert t["hook_outputs"] == 1 and t["hook_first_output"] == "only this"


def test_a_stream_without_hook_events_reports_none(tmp_path, monkeypatch):
    t = _t(tmp_path, monkeypatch, [_asst(1)])
    assert t["hook_outputs"] == 0 and t["hook_first_output"] is None


def test_a_non_json_hook_output_is_kept_as_it_is(tmp_path, monkeypatch):
    e = {"type": "system", "subtype": "hook_response", "output": "plain text from a hook"}
    assert _t(tmp_path, monkeypatch, [e, _asst(1)])["hook_first_output"] == "plain text from a hook"


def test_the_table_prints_hook_outputs_per_run_and_unknown_for_old_rows(monkeypatch):
    monkeypatch.setattr(rt, "guard_rows", lambda s: [])
    base = {"run": "x-main-r1", "issue": "9", "arm": "main", "rep": "1", "turns": 3, "calls": {}, "ctx_tokens": 1, "cost": 1.0, "seconds": 60,
            "suite_pass": True, "devkb_nav": 0, "devkb_selftest": 0, "acceptance": {"pass": True}, "contaminated": []}
    assert "| unknown | unknown | unknown | 3.0 |" in rt.table([("9", [{**base, "hook_outputs": 3}])])
    assert "| unknown | unknown | unknown | unknown |" in rt.table([("9", [base])])
