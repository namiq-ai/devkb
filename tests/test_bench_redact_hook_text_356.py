"""#356: a benchmark result row holds no local path: the recorded hook text is redacted."""
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "policy"))
sb = importlib.import_module("storybench")


def _stream(tmp_path, cwd, text):
    ev = [{"type": "system", "subtype": "init", "session_id": "s", "cwd": cwd},
          {"type": "system", "subtype": "hook_response", "hook_event": "PreToolUse", "exit_code": 0,
           "output": json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}})},
          {"type": "assistant", "message": {"id": "m1", "usage": {"output_tokens": 1}, "content": []}}]
    p = tmp_path / "s.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in ev))
    return p


def test_the_checkout_and_the_home_directory_are_replaced_in_the_recorded_text(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "guardrail_actions", lambda s: (0, {}))
    home = str(Path.home())
    cwd = f"{home}/.cache/devkb/policy-work/p9-main-r1"
    t = sb.transcript(_stream(tmp_path, cwd, f"a search in a repository devkb serves ({cwd}); notes in {home}/x"))
    out = t["hook_first_output"]
    assert "<checkout>" in out and cwd not in out and home not in out and "~/x" in out


def test_text_without_paths_is_unchanged_and_a_missing_root_still_redacts_the_home(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "guardrail_actions", lambda s: (0, {}))
    assert sb.redact("plain reminder") == "plain reminder"
    assert sb.redact(f"{Path.home()}/a/b", None) == "~/a/b"


def test_no_committed_result_row_holds_a_home_directory_path():
    """The scan the ticket asks for: rows under bench/policy (the baseline and the re-run) carry no home directory path."""
    here = Path(__file__).resolve().parents[1] / "bench" / "policy"
    rows = [*here.glob("results-*.jsonl"), *here.glob("rerun-*/results-*.jsonl")]
    bad = [f.name for f in rows if "/home/" in f.read_text() or "/Users/" in f.read_text()]
    assert bad == [], f"rows with a home directory path: {bad}"
